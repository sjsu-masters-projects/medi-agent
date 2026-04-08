import { Badge, Button, Card, Input } from "@/components/ui";

const settingsTabs = ["General Profile", "Team & Roles", "Patient Invites", "Integrations (MCP)"] as const;

const staff = [
    { email: "jane.doe@cityhealth.org", initials: "JD", name: "Jane Doe", role: "Clinic Admin", status: "Active", tone: "bg-slate-800 text-white" },
    { email: "d.smith@cityhealth.org", initials: "DS", name: "Dr. Smith", role: "Provider", status: "Active", tone: "bg-green-100 text-blue-700" },
    { email: "a.taylor@cityhealth.org", initials: "AT", name: "Amanda Taylor", role: "Nurse / MA", status: "Pending Invite", tone: "bg-purple-100 text-purple-700" },
];

export default function SettingsPage() {
    return (
        <div className="mx-auto max-w-7xl space-y-8">
            <div className="inline-flex rounded-xl border border-slate-200 bg-slate-100 p-1">
                {settingsTabs.map((tab) => (
                    <button
                        className={`rounded-lg px-5 py-2.5 text-sm ${tab === "Team & Roles" ? "bg-white font-semibold text-slate-900 shadow-sm" : "font-medium text-slate-600"}`}
                        key={tab}
                        type="button"
                    >
                        {tab}
                    </button>
                ))}
            </div>

            <div className="grid gap-8 xl:grid-cols-[2fr_1fr]">
                <div className="space-y-8">
                    <Card className="space-y-6">
                        <div>
                            <h2 className="text-2xl font-bold text-slate-900">Invite Team Member</h2>
                            <p className="mt-1 text-sm text-slate-500">Send an email invitation to add staff to your MediAgent workspace.</p>
                        </div>
                        <div className="grid gap-4 md:grid-cols-[1.3fr_0.8fr_auto] md:items-end">
                            <Input label="Email Address" placeholder="colleague@clinic.org" />
                            <label className="block">
                                <span className="mb-1 block text-sm font-bold uppercase tracking-[0.12em] text-slate-700">Role Access</span>
                                <select className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 shadow-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500">
                                    <option>Clinic Admin</option>
                                    <option>Provider</option>
                                    <option>Nurse / MA</option>
                                </select>
                            </label>
                            <Button className="h-[42px] px-6 font-semibold">Send Invite</Button>
                        </div>
                    </Card>

                    <Card className="overflow-hidden px-0 py-0" padding="sm">
                        <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-6 py-5">
                            <h3 className="text-xl font-bold text-slate-900">Active Staff (4)</h3>
                            <label className="relative block">
                                <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-slate-400">🔎</span>
                                <input
                                    className="w-64 rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm text-slate-700 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500"
                                    placeholder="Search team..."
                                />
                            </label>
                        </div>
                        <div className="grid grid-cols-[1.6fr_1fr_1fr_0.5fr] gap-4 border-b border-slate-200 bg-slate-50 px-6 py-4 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                            <span>Name &amp; Email</span>
                            <span>Role</span>
                            <span>Status</span>
                            <span className="text-right">Actions</span>
                        </div>
                        {staff.map((member, index) => (
                            <div className={`grid grid-cols-[1.6fr_1fr_1fr_0.5fr] gap-4 px-6 py-4 ${index > 0 ? "border-t border-slate-100" : ""}`} key={member.email}>
                                <div className="flex items-center gap-3">
                                    <div className={`flex h-10 w-10 items-center justify-center rounded-full text-xs font-bold ${member.tone}`}>{member.initials}</div>
                                    <div>
                                        <p className="text-sm font-bold text-slate-900">{member.name}</p>
                                        <p className="text-xs text-slate-500">{member.email}</p>
                                    </div>
                                </div>
                                <div className="flex items-center text-sm font-medium text-slate-700">{member.role}</div>
                                <div className="flex items-center">
                                    <Badge variant={member.status === "Active" ? "success" : "warning"}>{member.status}</Badge>
                                </div>
                                <div className="flex items-center justify-end text-slate-400">⋮</div>
                            </div>
                        ))}
                    </Card>
                </div>

                <div className="space-y-6">
                    <div className="rounded-xl border border-slate-700 bg-gradient-to-br from-slate-800 to-slate-950 p-6 text-white shadow-lg">
                        <h3 className="text-2xl font-bold">Patient Invite Code</h3>
                        <p className="mt-2 max-w-sm text-sm text-slate-300">
                            Share this unique code with patients so they can link their MediAgent mobile app to your clinic.
                        </p>
                        <div className="mt-6 flex items-center justify-between rounded-xl border border-slate-700 bg-slate-900/60 px-4 py-5">
                            <span className="text-3xl font-bold tracking-[0.14em]">CITY-8832</span>
                            <button className="rounded-md bg-slate-800 px-3 py-2 text-slate-300" type="button">
                                📋
                            </button>
                        </div>
                        <button
                            className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg border border-white/20 bg-white/10 px-4 py-3 text-sm font-medium text-white transition hover:bg-white/15"
                            type="button"
                        >
                            🖨️
                            <span>Print Handouts for Front Desk</span>
                        </button>
                    </div>

                    <Card className="space-y-4">
                        <div className="flex items-center justify-between">
                            <h3 className="text-xl font-bold text-slate-900">Clinic Profile</h3>
                            <button className="text-sm font-semibold text-blue-600" type="button">
                                Edit
                            </button>
                        </div>
                        <div className="space-y-4 text-sm">
                            <div>
                                <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">Clinic Name</p>
                                <p className="mt-1 font-medium text-slate-900">City Health Primary Care</p>
                            </div>
                            <div>
                                <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">NPI Number</p>
                                <p className="mt-1 font-medium text-slate-900">1234567890</p>
                            </div>
                            <div>
                                <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">Location</p>
                                <p className="mt-1 font-medium text-slate-900">123 Health Way, Suite 400</p>
                            </div>
                            <div className="border-t border-slate-100 pt-4">
                                <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">Default Document Sharing</p>
                                <div className="mt-2 inline-flex rounded-md bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-700">All Providers</div>
                            </div>
                        </div>
                    </Card>
                </div>
            </div>
        </div>
    );
}
