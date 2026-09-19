"""Deploy a Model Garden model for a working session and remove it when the session ends.

A GPU endpoint bills every hour it exists, whether or not anyone calls it. Deploying at the
start of a session and removing it at the end keeps a self-hosted model like MedGemma from
costing money while nobody is working.

    python scripts/model_garden_endpoint.py up \\
        --model publishers/google/models/medgemma@medgemma-1.5-4b-it \\
        --machine-type g2-standard-24 --accelerator-type NVIDIA_L4 --accelerator-count 2
    python scripts/model_garden_endpoint.py status
    python scripts/model_garden_endpoint.py down            # every endpoint this script created
    python scripts/model_garden_endpoint.py down --endpoint 1234567890

Endpoints created here get a display name starting with `session-`, and `down` without
`--endpoint` only removes endpoints with that prefix, so it never touches a deployment
someone else made. The machine type, accelerator type, and count must match one of the
model's verified Model Garden configurations.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

SESSION_PREFIX = "session-"
API = "https://{region}-aiplatform.googleapis.com/v1"


def build_deploy_body(
    *,
    model: str,
    machine_type: str,
    accelerator_type: str,
    accelerator_count: int,
    display_name: str,
) -> dict[str, Any]:
    """Request body for `projects.locations.deploy` with a single fixed replica."""
    return {
        "publisherModelName": model,
        "modelConfig": {"acceptEula": True},
        "endpointConfig": {"endpointDisplayName": display_name},
        "deployConfig": {
            "dedicatedResources": {
                "machineSpec": {
                    "machineType": machine_type,
                    "acceleratorType": accelerator_type,
                    "acceleratorCount": accelerator_count,
                },
                "minReplicaCount": 1,
                "maxReplicaCount": 1,
            }
        },
    }


def session_display_name(model: str, now: datetime) -> str:
    """`session-<model>-<UTC timestamp>`, trimmed to Vertex's display-name limit."""
    short = model.rsplit("/", 1)[-1].replace("@", "-").replace(".", "")
    return f"{SESSION_PREFIX}{short}-{now:%Y%m%d-%H%M}"[:128]


def select_session_endpoints(endpoints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Only the endpoints this script created."""
    return [e for e in endpoints if str(e.get("displayName", "")).startswith(SESSION_PREFIX)]


def openai_base_url(dedicated_dns: str) -> str:
    """Base URL for the vLLM OpenAI-compatible routes on a dedicated endpoint."""
    return f"https://{dedicated_dns}/v1"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--region", default="us-central1")
    commands = parser.add_subparsers(dest="command", required=True)

    up = commands.add_parser("up", help="Deploy a model and wait until it serves")
    up.add_argument(
        "--model", required=True, help="publishers/<publisher>/models/<model>@<version>"
    )
    up.add_argument("--machine-type", required=True)
    up.add_argument("--accelerator-type", required=True)
    up.add_argument("--accelerator-count", type=int, required=True)
    up.add_argument("--wait-minutes", type=int, default=60)

    commands.add_parser("status", help="List endpoints this script created")

    down = commands.add_parser("down", help="Undeploy and delete session endpoints")
    down.add_argument("--endpoint", help="Endpoint ID to remove, even if not created here")
    return parser.parse_args(argv)


class _Vertex:
    """Minimal authenticated client; credentials refresh themselves on expiry."""

    def __init__(self, region: str) -> None:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        from app.config import settings

        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        self.project = settings.google_project_id
        if not self.project:
            raise SystemExit("GOOGLE_PROJECT_ID is not configured")
        self.region = region
        self.base = API.format(region=region)
        self.session = AuthorizedSession(credentials)
        self.session.headers["x-goog-user-project"] = self.project

    def call(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.session.request(method, f"{self.base}/{path}", json=body, timeout=60)
        data: dict[str, Any] = response.json() if response.content else {}
        if response.status_code >= 400:
            message = data.get("error", {}).get("message", response.text[:300])
            raise SystemExit(f"{method} {path} failed with HTTP {response.status_code}: {message}")
        return data

    def wait(self, operation: dict[str, Any], minutes: int, label: str) -> dict[str, Any]:
        deadline = time.monotonic() + minutes * 60
        name = operation["name"]
        while True:
            current = self.call("GET", name)
            if current.get("done"):
                if "error" in current:
                    raise SystemExit(f"{label} failed: {current['error'].get('message')}")
                return current
            if time.monotonic() > deadline:
                raise SystemExit(f"{label} still running after {minutes} minutes: {name}")
            print(f"  {label}: waiting", flush=True)
            time.sleep(30)

    def endpoints(self) -> list[dict[str, Any]]:
        path = f"projects/{self.project}/locations/{self.region}/endpoints"
        return list(self.call("GET", path).get("endpoints", []))


def _up(client: _Vertex, args: argparse.Namespace) -> None:
    display_name = session_display_name(args.model, datetime.now(UTC))
    body = build_deploy_body(
        model=args.model,
        machine_type=args.machine_type,
        accelerator_type=args.accelerator_type,
        accelerator_count=args.accelerator_count,
        display_name=display_name,
    )
    print(f"Deploying {args.model} as {display_name}. GPU billing starts when replicas are up.")
    operation = client.call(
        "POST", f"projects/{client.project}/locations/{client.region}:deploy", body
    )
    done = client.wait(operation, args.wait_minutes, "deploy")
    endpoint_name = done.get("response", {}).get("endpoint", "")
    _describe(client, endpoint_name)
    print("Run `python scripts/model_garden_endpoint.py down` when the session ends.")


def _describe(client: _Vertex, endpoint_name: str) -> None:
    endpoint = client.call("GET", endpoint_name)
    dns = endpoint.get("dedicatedEndpointDns", "")
    print(f"endpoint: {endpoint_name}")
    print(f"display name: {endpoint.get('displayName')}")
    for deployed in endpoint.get("deployedModels", []):
        spec = deployed.get("dedicatedResources", {}).get("machineSpec", {})
        print(
            f"  deployed model {deployed.get('id')}: {spec.get('machineType')} "
            f"{spec.get('acceleratorType')}x{spec.get('acceleratorCount')} since {deployed.get('createTime')}"
        )
    if dns:
        print(f"OpenAI-compatible base URL: {openai_base_url(dns)}")


def _status(client: _Vertex) -> None:
    sessions = select_session_endpoints(client.endpoints())
    if not sessions:
        print("No session endpoints. Nothing is billing from this script.")
    for endpoint in sessions:
        _describe(client, endpoint["name"])


def _down(client: _Vertex, args: argparse.Namespace) -> None:
    if args.endpoint:
        path = f"projects/{client.project}/locations/{client.region}/endpoints/{args.endpoint}"
        targets = [client.call("GET", path)]
    else:
        targets = select_session_endpoints(client.endpoints())
    if not targets:
        print("No session endpoints to remove.")
        return
    for endpoint in targets:
        name = endpoint["name"]
        for deployed in endpoint.get("deployedModels", []):
            print(f"Undeploying model {deployed['id']} from {endpoint.get('displayName')}")
            operation = client.call(
                "POST", f"{name}:undeployModel", {"deployedModelId": deployed["id"]}
            )
            client.wait(operation, 30, "undeploy")
        print(f"Deleting endpoint {endpoint.get('displayName')}")
        client.wait(client.call("DELETE", name), 15, "delete endpoint")
    print("Done. No GPU is billing from these endpoints.")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    client = _Vertex(args.region)
    handlers: dict[str, Callable[[], None]] = {
        "up": lambda: _up(client, args),
        "status": lambda: _status(client),
        "down": lambda: _down(client, args),
    }
    handlers[args.command]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
