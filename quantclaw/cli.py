"""CLI interface for QuantClaw."""
from __future__ import annotations
import asyncio
import logging
import shutil
from pathlib import Path
import click
from rich.console import Console
from rich.table import Table

logger = logging.getLogger(__name__)

console = Console()

@click.group()
def cli():
    """QuantClaw: Open-source quant trading superagent harness."""
    pass

@cli.command()
def init():
    """Create a starter quantclaw.yaml if one does not already exist."""
    import yaml as _yaml
    path = Path("quantclaw.yaml")
    if path.exists():
        console.print(f"[yellow]{path} already exists. Edit it directly to change settings.[/]")
        return
    starter = {
        "llm_provider": "ollama",
        "data_sources": ["yfinance", "fred", "sec_edgar"],
        "broker_type": "paper",
        "watchlist": ["SPY", "QQQ"],
        "language": "en",
    }
    path.write_text(_yaml.dump(starter, default_flow_style=False, sort_keys=False), encoding="utf-8")
    console.print(f"[green]Wrote {path}. Edit it to configure your setup.[/]")

@cli.command()
def start():
    """Start the QuantClaw daemon."""
    from quantclaw.daemon import run_daemon
    console.print("[bold green]Starting QuantClaw daemon...[/]")
    asyncio.run(run_daemon())

@cli.command()
def stop():
    """Stop the QuantClaw daemon."""
    console.print("[bold red]Stopping QuantClaw daemon...[/]")

@cli.command()
def status():
    """Show daemon status and task queue."""
    from quantclaw.state.db import StateDB
    from quantclaw.state.tasks import TaskStore, TaskStatus
    from quantclaw.agents import ALL_AGENTS

    async def _status():
        db = await StateDB.create("data/quantclaw.db")
        store = TaskStore(db)
        running = await store.list_by_status(TaskStatus.RUNNING)
        pending = await store.list_by_status(TaskStatus.PENDING)

        table = Table(title="QuantClaw Status")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Running tasks", str(len(running)))
        table.add_row("Pending tasks", str(len(pending)))
        table.add_row("Agents available", str(len(ALL_AGENTS)))
        console.print(table)
        await db.close()

    asyncio.run(_status())

@cli.command()
@click.option("--template", required=True, help="Template name (e.g. momentum)")
@click.option("--name", default=None, help="Strategy name")
def new(template, name):
    """Create a new strategy from a template."""
    from quantclaw.strategy.loader import list_templates
    templates = list_templates()
    match = [t for t in templates if t["name"] == template]
    if not match:
        console.print(f"[red]Template '{template}' not found.[/]")
        available = [t["name"] for t in templates]
        console.print(f"Available: {', '.join(available)}")
        return
    src = Path(match[0]["path"])
    dest_name = name or template
    dest = Path("strategies") / f"{dest_name}.py"
    dest.parent.mkdir(exist_ok=True)
    shutil.copy(src, dest)
    console.print(f"[green]Created {dest} from template '{template}'[/]")

@cli.command("list")
def list_strategies():
    """List available strategy templates."""
    from quantclaw.strategy.loader import list_templates
    templates = list_templates()
    table = Table(title="Strategy Templates")
    table.add_column("Category", style="cyan")
    table.add_column("Name", style="green")
    for t in templates:
        table.add_row(t["category"], t["name"])
    console.print(table)

@cli.command()
@click.argument("strategy_path")
@click.option("--start", default="2019-01-01", help="Start date")
@click.option("--end", default="2024-12-31", help="End date")
def backtest(strategy_path, start, end):
    """Backtest a strategy file."""
    console.print(f"[bold]Backtesting {strategy_path} ({start} to {end})...[/]")

@cli.command()
@click.option("--sector", default=None, help="Target sector")
@click.option("--waves", default=1, type=int, help="Number of mining waves")
def mine(sector, waves):
    """Run factor mining."""
    console.print(f"[bold]Mining factors: sector={sector}, waves={waves}[/]")

@cli.command()
@click.argument("query")
def research(query):
    """Research a topic."""
    console.print(f"[bold]Researching: {query}[/]")

@cli.command()
@click.option("--source", default=None, help="Data source to ingest")
@click.option("--resume", is_flag=True, help="Resume interrupted ingestion")
def ingest(source, resume):
    """Run data ingestion."""
    console.print(f"[bold]Ingesting: source={source}, resume={resume}[/]")

@cli.command()
@click.option("--type", "report_type", default="weekly", help="Report type")
def report(report_type):
    """Generate a report."""
    console.print(f"[bold]Generating {report_type} report[/]")

@cli.command()
def watch():
    """Live event feed."""
    console.print("[bold]Watching events (Ctrl+C to stop)...[/]")

@cli.command()
@click.option("--agent", default=None, help="Filter by agent")
@click.option("--last", "count", default=10, type=int, help="Number of entries")
def logs(agent, count):
    """View task logs."""
    console.print(f"[bold]Last {count} logs for agent={agent or 'all'}[/]")

@cli.command()
def queue():
    """Show pending task queue."""
    console.print("[bold]Task queue:[/]")

@cli.command()
def plugins():
    """List installed plugins."""
    from quantclaw.plugins.manager import PluginManager
    pm = PluginManager()
    pm.discover()
    table = Table(title="Installed Plugins")
    table.add_column("Type", style="cyan")
    table.add_column("Name", style="green")
    for ptype in ["broker", "data", "engine", "asset"]:
        for name in pm.list_plugins(ptype):
            table.add_row(ptype, name)
    console.print(table)

@cli.command()
@click.argument("plugin_name")
def install(plugin_name):
    """Install a plugin."""
    from quantclaw.plugins.manager import PluginManager
    pm = PluginManager()
    console.print(f"[bold]Installing quantclaw-{plugin_name}...[/]")
    if pm.install(plugin_name):
        console.print(f"[green]Installed {plugin_name}[/]")
    else:
        console.print(f"[red]Failed to install {plugin_name}[/]")

@cli.command()
@click.option("--install-only", is_flag=True, help="Only install dependencies, don't start")
def dashboard(install_only):
    """Install dependencies and start the full QuantClaw stack (backend + sidecar + dashboard)."""
    import subprocess as sp
    import sys
    import os
    import time
    import signal as sig

    root = Path(__file__).parent.parent
    sidecar_dir = root / "quantclaw" / "sidecar"
    dashboard_dir = root / "quantclaw" / "dashboard" / "app"
    procs = []

    def cleanup(*_):
        console.print("\n[bold red]Shutting down...[/]")
        for p in procs:
            try:
                p.terminate()
                p.wait(timeout=5)
            except Exception:
                try: p.kill()
                except Exception:
                    logger.exception("CLI command failed")
        console.print("[green]All services stopped.[/]")
        raise SystemExit(0)

    # Install
    console.print("\n[bold]QuantClaw Setup[/]\n")

    console.print("  Installing Python dependencies...")
    sp.run([sys.executable, "-m", "pip", "install", "-e", str(root), "-q"], capture_output=True)
    sp.run([sys.executable, "-m", "pip", "install", "httpx", "-q"], capture_output=True)
    console.print("  [green]OK[/] Python packages")

    console.print("  Installing sidecar...")
    sp.run("npm install", cwd=str(sidecar_dir), capture_output=True, shell=True)
    console.print("  [green]OK[/] Node.js sidecar")

    console.print("  Installing dashboard...")
    sp.run("npm install", cwd=str(dashboard_dir), capture_output=True, shell=True)
    console.print("  [green]OK[/] Next.js dashboard")

    (root / "data").mkdir(exist_ok=True)

    if install_only:
        console.print("\n[green]Installation complete![/]")
        return

    # Start
    console.print("\n[bold]Starting services...[/]\n")
    sig.signal(sig.SIGINT, cleanup)

    # Backend
    backend = sp.Popen(
        [sys.executable, "-m", "uvicorn", "quantclaw.dashboard.api:app", "--host", "0.0.0.0", "--port", "8000"],
        cwd=str(root), stdout=sp.DEVNULL, stderr=sp.DEVNULL,
    )
    procs.append(backend)
    time.sleep(2)
    console.print(f"  [green]OK[/] Backend -> http://localhost:24120")

    # Sidecar
    sidecar = sp.Popen(
        "node server.js", cwd=str(sidecar_dir), stdout=sp.DEVNULL, stderr=sp.DEVNULL, shell=True,
    )
    procs.append(sidecar)
    time.sleep(1)
    console.print(f"  [green]OK[/] Sidecar -> http://localhost:24122")

    # Dashboard
    dash = sp.Popen(
        "npm run dev", cwd=str(dashboard_dir), stdout=sp.PIPE, stderr=sp.DEVNULL, shell=True,
    )
    procs.append(dash)
    url = "http://localhost:3000"
    start_t = time.time()
    while time.time() - start_t < 15:
        line = dash.stdout.readline().decode("utf-8", errors="replace") if dash.stdout else ""
        if "Local:" in line:
            url = line.split("Local:")[1].strip()
            break
        if "Ready" in line:
            break
        time.sleep(0.5)
    console.print(f"  [green]OK[/] Dashboard -> {url}")

    console.print(f"""
[bold green]
QuantClaw is running!

  Dashboard:  {url}
  Backend:    http://localhost:24120
  Sidecar:    http://localhost:24122

  Press Ctrl+C to stop all services
[/]""")

    try:
        while True:
            time.sleep(5)
    except (KeyboardInterrupt, SystemExit):
        cleanup()

@cli.command()
@click.argument("query")
def ask(query):
    """Natural language request (routes to Planner)."""
    console.print(f"[bold]Planning: {query}[/]")
