---
description: How to add a new AI agent to the LangGraph system
---

# Adding a New Agent

## Pre-requisites
- Read `.agent/ARCHITECTURE.md` (Agent Flow section)
- Read existing agents in `backend/app/agents/` for patterns
- Understand LangGraph state management

## Steps

1. **Define the agent's contract**
   - What triggers it? (user action, cron, another agent)
   - What input does it receive?
   - What output does it produce?
   - What tools does it need?
   - Which LLM? (Flash for speed, Pro for reasoning)

2. **Create the agent file**
   ```
   backend/app/agents/{agent_name}.py
   ```
   - Extend `BaseAgent` from `backend/app/agents/base.py`
   - Define LangGraph state schema
   - Define graph nodes (each node = one step)
   - Define edges (routing logic)
   - Implement `process()` method

3. **Create any new tools**
   ```
   backend/app/tools/{tool_name}.py
   ```
   - Each tool is a function that the agent can call
   - Tools handle external API calls, DB queries, or data transformations
   - Tools must have clear input/output types
   - Tools must handle errors gracefully

4. **Create the router endpoint**
   - Add API route that triggers the agent
   - Or connect to existing trigger (Triage routing, cron scheduler)

5. **Write tests**
   - Golden-set: curated input/output pairs
   - Unit tests for individual tools
   - Integration test: trigger → agent → output → database

6. **Update documentation**
   - Add agent to ARCHITECTURE.md Agent Flow section
   - Update PROJECT.md agent table
   - Update TASKS.md with completed status

## Agent Pattern Template

```python
from app.agents.base import BaseAgent, AgentInput, AgentOutput
from langgraph.graph import StateGraph, END

class NewAgent(BaseAgent):
    """One-line description of what this agent does."""

    def __init__(self, llm: LLMClient, tools: dict):
        self.llm = llm
        self.tools = tools
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)
        graph.add_node("step_1", self._step_1)
        graph.add_node("step_2", self._step_2)
        graph.add_edge("step_1", "step_2")
        graph.add_edge("step_2", END)
        graph.set_entry_point("step_1")
        return graph.compile()

    async def _step_1(self, state: AgentState) -> AgentState:
        # First processing step
        ...

    async def _step_2(self, state: AgentState) -> AgentState:
        # Second processing step
        ...

    async def process(self, input: AgentInput) -> AgentOutput:
        result = await self.graph.ainvoke(input)
        return AgentOutput(...)
```
