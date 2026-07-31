import asyncio
import json
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import box

from .client import AsyncUBN
from .config import Config
from .exceptions import UBNError, UBNAuthError, UBNRateLimitError
from .utils import console, print_error, print_success, print_warning, print_info


# ---------- Група команд ----------
@click.group()
@click.pass_context
def cli(ctx):
    """UBN Async SDK – manage bot network."""
    ctx.ensure_object(dict)
    ctx.obj['config'] = Config()
    ctx.obj['config'].load()


# ---------- init ----------
@cli.command()
@click.option('--base-url', default=None, help='UBN API base URL')
def init(base_url):
    """Interactive registration."""
    # Welcome
    console.print(Panel(
        "[bold]UBN Registration[/bold]\n"
        "Your bot will publish presence in chats and see other bots.",
        border_style="cyan"
    ))

    # Base URL
    if not base_url:
        base_url = input("API URL (default: https://kit.felixcard.online/net): ").strip()
        if not base_url:
            base_url = "https://kit.felixcard.online/net"

    # Bot name
    name = input("Bot name: ").strip()
    while not name:
        print_error("Name cannot be empty.")
        name = input("Bot name: ").strip()

    # Bot type
    print("\nBot type:")
    print("  1 - Telegram bot (works in chats)")
    print("  2 - Service/application (not Telegram)")
    while True:
        type_choice = input("Choose 1 or 2: ").strip()
        if type_choice == "1":
            app_type = "telegram"
            break
        elif type_choice == "2":
            app_type = "service"
            break
        else:
            print_error("Invalid choice. Enter 1 or 2.")

    # Access level
    print("\nAccess level (what you publish):")
    print("  1 - Presence: activity only (0-100)")
    print("  2 - Shared Data: activity + extra stats")
    print("  3 - Custom Integration: full custom data (up to 2KB)")
    while True:
        level_choice = input("Choose 1, 2 or 3: ").strip()
        if level_choice in ("1", "2", "3"):
            default_level = int(level_choice)
            break
        else:
            print_error("Invalid choice. Enter 1, 2 or 3.")

    # Optional fields (skip with Enter)
    bot_username = input("Telegram username (optional, e.g. @mybot): ").strip() or None
    owner_id = input("Your Telegram ID (optional): ").strip() or None

    # Confirmation
    print("\nReview:")
    console.print(f"  Name: {name}")
    console.print(f"  Type: {app_type}")
    console.print(f"  Level: {default_level}")
    if bot_username:
        console.print(f"  Username: {bot_username}")
    if owner_id:
        console.print(f"  Owner ID: {owner_id}")
    console.print(f"  API URL: {base_url}")

    confirm = input("\nProceed? (y/n): ").strip().lower()
    if confirm != 'y':
        print_info("Registration cancelled.")
        return

    # Registration
    async def _register():
        async with AsyncUBN(base_url=base_url) as client:
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
                task = progress.add_task("Registering...", total=None)
                try:
                    result = await client.register(
                        name=name,
                        app_type=app_type,
                        default_level=default_level,
                        bot_username=bot_username,
                        owner_telegram_id=owner_id,
                        save_config=True,
                    )
                    progress.update(task, completed=1)
                    return result
                except UBNError as e:
                    progress.update(task, completed=1)
                    raise e

    try:
        result = asyncio.run(_register())
        print_success("Registration successful!")
        console.print(f"Public ID: {result['publicId']}")
        console.print(f"API Key: [yellow]{result['apiKey']}[/yellow] (save it!)")
        console.print("[dim]Config saved to .ubn/config.json and .env[/dim]")
    except UBNError as e:
        print_error(f"Registration error: {e}")
    except Exception as e:
        print_error(f"Unexpected error: {e}")


# ---------- info ----------
@cli.command()
@click.argument('public_id', required=False)
@click.pass_context
def info(ctx, public_id):
    """Show bot info (own or by public_id)."""
    config = ctx.obj['config']
    try:
        async def _info():
            async with AsyncUBN() as client:
                if public_id:
                    profile = await client.get_public_profile(public_id)
                    if not profile:
                        print_error(f"Bot {public_id} not found")
                        return
                    console.print(Panel(f"[bold cyan]Profile of {public_id}[/bold cyan]", border_style="cyan"))
                    _print_profile(profile)
                    schemas = await client.list_schemas(public_id)
                    if schemas:
                        console.print("\n[bold]Published schemas:[/bold]")
                        _print_schemas(schemas)
                else:
                    profile = await client.get_my_profile()
                    if not profile:
                        print_error("Failed to get profile. Token might be invalid.")
                        return
                    console.print(Panel("[bold cyan]My profile[/bold cyan]", border_style="cyan"))
                    _print_profile(profile)
                    schemas = await client.list_schemas(config.get_public_id())
                    if schemas:
                        console.print("\n[bold]My schemas:[/bold]")
                        _print_schemas(schemas)
                    grants = await client.list_grants()
                    if grants:
                        console.print("\n[bold]Grants issued:[/bold]")
                        _print_grants(grants)
                    webhooks = await client.list_webhooks()
                    if webhooks:
                        console.print("\n[bold]Webhooks:[/bold]")
                        _print_webhooks(webhooks)
        asyncio.run(_info())
    except Exception as e:
        print_error(f"Error: {e}")


def _print_profile(profile: dict):
    table = Table(box=box.ROUNDED, show_header=False)
    table.add_column("Field", style="bold cyan")
    table.add_column("Value")
    for key, value in profile.items():
        if key in ('createdAt', 'updatedAt'):
            continue
        if isinstance(value, list):
            value = ", ".join(value)
        table.add_row(key, str(value))
    console.print(table)


def _print_schemas(schemas: list):
    table = Table(title="Schemas", box=box.ROUNDED)
    table.add_column("Capability", style="cyan")
    table.add_column("Version")
    table.add_column("Updated")
    for s in schemas:
        table.add_row(s.get('capability', ''), s.get('schemaVersion', ''), str(s.get('updatedAt', '')))
    console.print(table)


def _print_grants(grants: list):
    table = Table(title="Grants", box=box.ROUNDED)
    table.add_column("Grantee", style="cyan")
    table.add_column("Level")
    for g in grants:
        table.add_row(g.get('granteePublicId', ''), str(g.get('level', '')))
    console.print(table)


def _print_webhooks(webhooks: list):
    table = Table(title="Webhooks", box=box.ROUNDED)
    table.add_column("ID", style="cyan")
    table.add_column("URL")
    table.add_column("Events")
    for w in webhooks:
        table.add_row(w.get('id', ''), w.get('url', ''), ", ".join(w.get('events', [])))
    console.print(table)


# ---------- presence ----------
@cli.group()
def presence():
    """Manage presence in chats."""
    pass


@presence.command('publish')
@click.option('--file', 'file_path', type=click.Path(exists=True), help='JSON file with chats array')
@click.option('--chat', 'chat_data', multiple=True, help='Single chat in format chatId:level:data (data JSON)')
@click.option('--auto-batch/--no-batch', default=True, help='Auto-split into batches of 50')
def presence_publish(file_path, chat_data, auto_batch):
    """Publish presence in chats."""
    chats = []
    if file_path:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                chats = data
            elif isinstance(data, dict) and 'chats' in data:
                chats = data['chats']
            else:
                print_error("File must contain array or object with 'chats' key")
                return
    if chat_data:
        for item in chat_data:
            parts = item.split(':', 2)
            if len(parts) != 3:
                print_error(f"Invalid format: {item}. Expected chatId:level:data")
                return
            chat_id, level_str, data_str = parts
            try:
                level = int(level_str)
                data_obj = json.loads(data_str)
            except Exception as e:
                print_error(f"Parse error: {e}")
                return
            chats.append({"chatId": chat_id, "level": level, "data": data_obj})
    if not chats:
        print_error("No chats specified.")
        return

    async def _publish():
        async with AsyncUBN() as client:
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
                task = progress.add_task("Publishing...", total=len(chats))
                results = await client.publish_presence(chats, auto_batch=auto_batch)
                progress.update(task, completed=len(chats))
            total_updated = sum(r.get('updated', 0) for r in results)
            total_failed = sum(len(r.get('failed', [])) for r in results)
            print_success(f"Updated: {total_updated}, failed: {total_failed}")
            if total_failed:
                for r in results:
                    for fail in r.get('failed', []):
                        print_warning(f"Chat {fail.get('chatId')}: {fail.get('error')}")
    asyncio.run(_publish())


@presence.command('get')
@click.argument('chat_ids', nargs=-1, required=True)
def presence_get(chat_ids):
    """Get presence of other bots in chats."""
    if not chat_ids:
        print_error("Specify at least one chatId")
        return

    async def _get():
        async with AsyncUBN() as client:
            result = await client.get_presence(list(chat_ids))
            if result.get('chats'):
                console.print("[bold]Presence:[/bold]")
                for chat_id, entries in result['chats'].items():
                    console.print(f"\n[cyan]{chat_id}[/cyan]")
                    table = Table(box=box.ROUNDED)
                    table.add_column("Bot", style="cyan")
                    table.add_column("Level")
                    table.add_column("Data")
                    for entry in entries:
                        table.add_row(
                            entry.get('botPublicId', ''),
                            str(entry.get('level', '')),
                            json.dumps(entry.get('data', {}), ensure_ascii=False)
                        )
                    console.print(table)
            if result.get('skipped') and result['skipped'].get('chatIds'):
                print_warning(f"Skipped chats: {', '.join(result['skipped']['chatIds'])}")
    asyncio.run(_get())


# ---------- grants ----------
@cli.group()
def grants():
    """Manage partner grants."""
    pass


@grants.command('list')
def grants_list():
    """List issued grants."""
    async def _list():
        async with AsyncUBN() as client:
            grants = await client.list_grants()
            if not grants:
                print_info("No grants")
                return
            _print_grants(grants)
    asyncio.run(_list())


@grants.command('add')
@click.argument('grantee_public_id')
@click.argument('level', type=int)
def grants_add(grantee_public_id, level):
    """Add a grant for partner."""
    async def _add():
        async with AsyncUBN() as client:
            await client.create_grant(grantee_public_id, level)
            print_success(f"Grant for {grantee_public_id} level {level} created")
    asyncio.run(_add())


@grants.command('remove')
@click.argument('grantee_public_id')
def grants_remove(grantee_public_id):
    """Revoke a grant."""
    async def _remove():
        async with AsyncUBN() as client:
            await client.revoke_grant(grantee_public_id)
            print_success(f"Grant for {grantee_public_id} revoked")
    asyncio.run(_remove())


# ---------- webhooks ----------
@cli.group()
def webhooks():
    """Manage webhooks."""
    pass


@webhooks.command('list')
def webhooks_list():
    """List webhook subscriptions."""
    async def _list():
        async with AsyncUBN() as client:
            wh = await client.list_webhooks()
            if not wh:
                print_info("No webhooks")
                return
            _print_webhooks(wh)
    asyncio.run(_list())


@webhooks.command('add')
@click.argument('url')
@click.argument('events', nargs=-1, required=True)
def webhooks_add(url, events):
    """Add webhook. Events: grant_received, grant_revoked, bot_verified."""
    async def _add():
        async with AsyncUBN() as client:
            result = await client.create_webhook(url, list(events))
            print_success(f"Webhook added. ID: {result.get('webhookId')}")
            if 'secret' in result:
                console.print(f"[bold]Secret:[/bold] [yellow]{result['secret']}[/yellow] (save it!)")
    asyncio.run(_add())


@webhooks.command('remove')
@click.argument('webhook_id')
def webhooks_remove(webhook_id):
    """Delete webhook by ID."""
    async def _remove():
        async with AsyncUBN() as client:
            await client.delete_webhook(webhook_id)
            print_success(f"Webhook {webhook_id} deleted")
    asyncio.run(_remove())


# ---------- schemas ----------
@cli.group()
def schemas():
    """Manage data contracts (schemas)."""
    pass


@schemas.command('list')
@click.argument('public_id', required=False)
def schemas_list(public_id):
    """List schemas (own or by public_id)."""
    async def _list():
        async with AsyncUBN() as client:
            pid = public_id or client.config.get_public_id()
            schemas = await client.list_schemas(pid)
            if not schemas:
                print_info("No schemas found")
                return
            _print_schemas(schemas)
    asyncio.run(_list())


@schemas.command('publish')
@click.argument('capability')
@click.argument('version')
@click.argument('schema_file', type=click.Path(exists=True))
def schemas_publish(capability, version, schema_file):
    """Publish schema from JSON file."""
    try:
        with open(schema_file, 'r', encoding='utf-8') as f:
            schema = json.load(f)
    except Exception as e:
        print_error(f"File read error: {e}")
        return

    async def _publish():
        async with AsyncUBN() as client:
            await client.publish_schema(capability, version, schema)
            print_success(f"Schema '{capability}' v{version} published")
    asyncio.run(_publish())


@schemas.command('get')
@click.argument('public_id')
@click.argument('capability')
def schemas_get(public_id, capability):
    """Get specific schema of a bot."""
    async def _get():
        async with AsyncUBN() as client:
            schema = await client.get_schema(public_id, capability)
            if schema:
                console.print_json(json.dumps(schema, ensure_ascii=False, indent=2))
            else:
                print_warning("Schema not found")
    asyncio.run(_get())


# ---------- profile ----------
@cli.group()
def profile():
    """Manage profile."""
    pass


@profile.command('show')
def profile_show():
    """Show current profile."""
    async def _show():
        async with AsyncUBN() as client:
            profile = await client.get_my_profile()
            if not profile:
                print_error("Failed to get profile")
                return
            _print_profile(profile)
    asyncio.run(_show())


@profile.command('update')
@click.option('--bio', help='Short description')
@click.option('--capabilities', help='Comma-separated capabilities (games,stickers)')
@click.option('--features', help='Comma-separated features (presence,storage)')
def profile_update(bio, capabilities, features):
    """Update profile."""
    caps = capabilities.split(',') if capabilities else None
    feats = features.split(',') if features else None

    async def _update():
        async with AsyncUBN() as client:
            await client.update_profile(bio=bio, capabilities=caps, features=feats)
            print_success("Profile updated")
    asyncio.run(_update())


# ---------- discover ----------
@cli.command('discover')
@click.option('--capability', help='Filter by capability')
@click.option('--type', 'bot_type', help='Bot type (telegram/service)')
@click.option('--feature', help='Filter by feature')
@click.option('--features', help='Multiple features comma-separated')
def discover(capability, bot_type, feature, features):
    """Search bots in catalog."""
    async def _discover():
        async with AsyncUBN() as client:
            bots = await client.discover_bots(
                capability=capability,
                bot_type=bot_type,
                feature=feature,
                features=features,
            )
            if not bots:
                print_info("No bots found")
                return
            table = Table(title="Found bots", box=box.ROUNDED)
            table.add_column("Public ID", style="cyan")
            table.add_column("Name")
            table.add_column("Type")
            table.add_column("Capabilities")
            table.add_column("Verified")
            for b in bots:
                table.add_row(
                    b.get('publicId', ''),
                    b.get('name', ''),
                    b.get('type', ''),
                    ", ".join(b.get('capabilities', [])),
                    "yes" if b.get('verified') else "no"
                )
            console.print(table)
    asyncio.run(_discover())


# ---------- rotate-key ----------
@cli.command('rotate-key')
def rotate_key():
    """Regenerate API key."""
    async def _rotate():
        async with AsyncUBN() as client:
            result = await client.rotate_key()
            if result.get('ok'):
                print_success("Key rotated")
                console.print(f"[bold]New API Key:[/bold] [yellow]{result['apiKey']}[/yellow] (save it!)")
            else:
                print_error("Rotation failed")
    asyncio.run(_rotate())


# ---------- health ----------
@cli.command('health')
def health():
    """Check server status."""
    async def _health():
        async with AsyncUBN() as client:
            try:
                result = await client.health()
                if result.get('ok'):
                    print_success("Server is up")
                else:
                    print_warning("Server responded with error")
            except Exception as e:
                print_error(f"Connection failed: {e}")
    asyncio.run(_health())


# ---------- flush ----------
@cli.command('flush')
def flush():
    """Send queued requests immediately."""
    async def _flush():
        async with AsyncUBN() as client:
            count = await client.flush_queued(silent=False)
            if count:
                print_success(f"Sent {count} queued requests")
            else:
                print_info("Queue is empty")
    asyncio.run(_flush())


# ---------- main ----------
def main():
    cli()


if __name__ == "__main__":
    main()