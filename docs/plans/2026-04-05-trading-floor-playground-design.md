# Trading Floor Playground — Design Document

**Date:** 2026-04-05
**Status:** Approved
**Author:** Harry + Claude

## Overview

Replace the QuantClaw dashboard home page with a live, interactive 2D canvas visualization of all 13 AI trading agents working on a virtual trading floor. The user is the CEO of a quant trading firm. Inspired by Stanford's Generative Agents but themed as a quant trading office.

## Layout

```
+--sidebar--+--------Trading Floor Canvas--------+----Chat Panel----+
|           |                                      |                  |
| nav       |   [Canvas: 13 agent stations]        | Chat with        |
| links     |   [Mode toggle top-left]             | Scheduler /      |
|           |   [Status bar bottom]                | @agent           |
|           |                                      |                  |
|           |   Click any agent to talk             | [input: @agent]  |
+-----------+--------------------------------------+------------------+
```

- **Center (65%)**: HTML5 Canvas rendering the trading floor
- **Right (35%)**: Persistent chat panel with @mention input
- **Top-left overlay**: Visual mode toggle (pixel / isometric / modern)
- **Bottom overlay**: Floor status bar (active tasks, market status, time)

## Rendering Approach

HTML5 Canvas + sprite sheets. React wraps the canvas and handles the chat panel + overlays. Switching visual modes swaps sprite sheets only — all logic, positions, and state stay the same.

### Three Visual Modes

| Mode | Style | Aesthetic |
|------|-------|-----------|
| Pixel | 16-bit retro RPG | Dark tiled floor, pixel walls, 32x32 characters, chunky props |
| Isometric | SimCity / office sim | 2.5D diamond tiles, depth-sorted, angled desks |
| Modern | Flat vector / stylized | Smooth dark surfaces, clean vector characters, neon accents, matches dashboard |

Default mode: Modern. Preference saved to localStorage. Transition: 0.3s fade.

### Sprite Sheet Architecture

```
sprites/
  pixel/
    agents.png, stations.png, floor.png, effects.png
  isometric/
    agents.png, stations.png, floor.png, effects.png
  modern/
    agents.png, stations.png, floor.png, effects.png
```

## Trading Floor Map

Single open-plan floor with 13 themed stations in logical zones:

### Command Center
- **Scheduler**: Reception desk with workflow board. Megaphone for broadcasts. The CEO's chief of staff.
- **Sentinel**: Watchtower with radar screens and binoculars. Always-on daemon.

### Data Room
- **Ingestor**: Data pipes flowing into monitors, satellite dish. Numbers streaming.

### Quant Lab
- **Backtester**: Time machine console with rewind dials and equity curve display.
- **Miner**: Pickaxe, ore cart, glowing crystals being extracted from rock.
- **Trainer**: Neural network visualization, brain in a jar, training progress bars.
- **Researcher**: Library desk with books, magnifying glass, papers, lightbulb.

### Trading Desk
- **Executor**: Bloomberg-style terminal, order blotter, flashing buy/sell lights.
- **Risk Monitor**: Dashboard with gauges, warning lights, shield icon.

### Back Office
- **Reporter**: Printing press, stacking papers, charts on wall.
- **Cost Tracker**: Calculator, ledger, coin stacks, budget gauge.
- **Compliance**: Filing cabinet, stamp, rulebook, scales of justice.

### Debug Bay
- **Debugger**: Workbench with magnifying glass, bug jar, circuit boards, log scrolls.

## Agent Behavior

Agents are **stationary** at their stations. No walking. Hybrid idle behavior: subtle animations at rest, active reactions on events.

### Agent States

| State | Visual | Trigger |
|-------|--------|---------|
| Idle | Subtle loop: typing, glancing at screen (2-3 frames, slow) | Default |
| Busy | Active animation: fast typing, tools moving, station-specific (4-6 frames, fast). Amber glow. Progress bar. | Task in progress |
| Complete | Green pulse, checkmark flash, data display updates | Task finished |
| Error | Red flash, warning icon, agent leans back (2 frames) | Task failed |

### Busy Animations Per Agent

| Agent | Animation |
|-------|-----------|
| Scheduler | Workflow board lights up, task cards shuffle, megaphone pulses on broadcast |
| Ingestor | Data pipes glow and flow, satellite dish spins, numbers stream |
| Miner | Pickaxe swings, sparks fly, glowing crystals pop out |
| Backtester | Time machine dials spin, equity curve draws, clock rewinds |
| Researcher | Pages flip, magnifying glass moves, lightbulb flashes |
| Risk Monitor | Gauges swing, warning lights cycle, shield pulses |
| Executor | Buy/sell lights flash, order tickets fly, terminal scrolls |
| Reporter | Printer outputs paper, charts draw on wall, papers stack |
| Trainer | Neural network nodes pulse, brain glows, training bar fills |
| Compliance | Stamp pounds, pages flip in rulebook, scales balance |
| Cost Tracker | Calculator buttons press, coins animate, budget gauge moves |
| Debugger | Magnifying glass scans, bugs caught in jar, circuit sparks |
| Sentinel | Radar sweeps, binoculars scan, alert beacon rotates |

### Station Anatomy

Each station displays:
- Character sprite with idle/busy animation
- Themed desk and props
- Name label below
- Status indicator: green (idle), amber pulse (busy), red flash (error)
- Mini data display: tiny screen with live data relevant to the agent
- Progress bar: appears when agent is working, shows percentage
- Speech bubble: appears on click or when agent communicates

### Locked Agents

All 13 stations visible. Locked agents: 50% opacity, character is a silhouette, lock icon overlay. Clicking shows "Unlock at Level X."

### Multi-Agent Delegation

Broadcast + parallel: Scheduler megaphone animation plays, pulse ring expands outward from Scheduler across the floor, target agents simultaneously light up and transition to Busy.

## Chat Panel

### Structure

- **Header**: Shows current agent avatar + name (default: Scheduler)
- **Messages**: Scrollable message thread with agent badges
- **Input**: Text input with @mention autocomplete

### @Mention System

| Input | Behavior |
|-------|----------|
| No @ | Goes to Scheduler (default). Scheduler delegates if needed. |
| `@backtester` | Direct message. Chat header switches. Speech bubble on canvas. |
| `@all` | Scheduler broadcasts to all enabled agents. |
| `@agent1 @agent2` | Scheduler coordinates both. Both light up on floor. |

### Autocomplete

Typing `@` opens dropdown listing all enabled agents with status (idle/busy). Locked agents greyed out with "Level X required."

### Click-to-Talk

Clicking an agent on the canvas:
- Highlights station with selection glow
- Auto-fills `@agentname` in chat input
- Expands any visible speech bubble

### CEO Experience

The Scheduler greets the user as CEO on first load. All unaddressed messages route through Scheduler, who acts as chief of staff / receptionist, delegating to the right agents.

## Data Flow

### WebSocket (Real-time)

Dashboard connects to `ws://localhost:8000/ws/events`. Events:

| Event | Floor Reaction |
|-------|---------------|
| `agent.task.started` | Busy state, progress bar, speech bubble |
| `agent.task.progress` | Progress bar update, mini display refresh |
| `agent.task.completed` | Complete animation, result in speech bubble + chat |
| `agent.task.failed` | Error animation, error in speech bubble + chat |
| `agent.broadcast` | Scheduler megaphone, pulse ring, targets light up |
| `market.data.update` | Ingestor pipes glow, tickers scroll |

### Chat Flow

```
User message -> POST /api/chat { message, agent, lang, provider, model }
  -> Backend routes, emits agent.task.started via WebSocket
  -> Canvas animates agent to Busy
  -> LLM responds, backend emits agent.task.completed
  -> Canvas animates Complete, speech bubble shows result
  -> Chat panel shows response with agent badge
```

### Fallback

WebSocket disconnect -> poll `GET /api/events` every 3 seconds.

### Floor Init

On load: `GET /api/agents` for agent list + status, `GET /api/tasks` for active tasks.

## Non-Requirements

- No audio / sound effects (silent, purely visual)
- No agent walking / pathfinding (stationary at stations)
- No physics simulation
- No persistent agent memory / generative behavior (agents respond to real tasks, not simulated social behavior)

## i18n

Reuses existing `useLang()` context. Agent names, status labels, chat messages, and UI overlays translated in EN/ZH/JA.

## Technical Dependencies

- HTML5 Canvas API (no external game engine)
- Sprite sheets (PNG) for each visual mode
- Existing WebSocket endpoint (`/ws/events`)
- Existing chat endpoint (`POST /api/chat`)
- Existing agent API (`GET /api/agents`)
- localStorage for mode preference
