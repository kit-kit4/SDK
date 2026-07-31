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
from rich.markdown import Markdown

from .client import AsyncUBN
from .config import Config
from .exceptions import UBNError, UBNAuthError, UBNRateLimitError
from .utils import console, print_error, print_success, print_warning, print_info, print_json, table_from_dicts, panel_text
from .schema import infer_schema, schema_hash

# Група команд
@click.group()
@click.pass_context
def cli(ctx):
    """UBN Async SDK – керування мережею ботів."""
    ctx.ensure_object(dict)
    ctx.obj['config'] = Config()
    ctx.obj['config'].load()

# ---------- init ----------
@cli.command()
@click.option('--name', prompt='Назва бота', help='Назва вашого бота')
@click.option('--type', 'app_type', default='telegram', prompt='Тип (telegram/service)', help='Тип бота')
@click.option('--level', 'default_level', default=1, prompt='Рівень доступу (1-3)', type=int, help='Default level')
@click.option('--username', 'bot_username', prompt='Ім\'я користувача (Telegram, опціонально)', default='', help='@username')
@click.option('--owner', 'owner_telegram_id', prompt='Telegram ID власника (опціонально)', default='', help='ID власника')
@click.option('--base-url', default=None, help='UBN API base URL')
def init(name, app_type, default_level, bot_username, owner_telegram_id, base_url):
    """Інтерактивна реєстрація нового бота."""
    console.print(Panel.fit("🚀 [bold cyan]UBN Registration[/bold cyan]", border_style="cyan"))
    try:
        async def _init():
            config = Config()
            config.load()
            base = base_url or config.base_url
            async with AsyncUBN(base_url=base) as client:
                result = await client.register(
                    name=name,
                    app_type=app_type,
                    default_level=default_level,
                    bot_username=bot_username or None,
                    owner_telegram_id=owner_telegram_id or None,
                    save_config=True,
                )
                return result
        result = asyncio.run(_init())
        print_success("Реєстрація успішна!")
        console.print(f"[bold]Public ID:[/bold] {result['publicId']}")
        console.print(f"[bold]API Key:[/bold] [yellow]{result['apiKey']}[/yellow] (збережіть!)")
        console.print("[dim]Конфігурацію збережено у .ubn/config.json та .env[/dim]")
    except Exception as e:
        print_error(f"Помилка реєстрації: {e}")

# ---------- info ----------
@cli.command()
@click.argument('public_id', required=False)
@click.pass_context
def info(ctx, public_id):
    """Показати інформацію про бота (свого або за public_id)."""
    config = ctx.obj['config']
    try:
        async def _info():
            async with AsyncUBN() as client:
                if public_id:
                    # Інформація про іншого бота
                    profile = await client.get_public_profile(public_id)
                    if not profile:
                        print_error(f"Бот {public_id} не знайдений")
                        return
                    console.print(Panel(f"[bold cyan]Профіль бота {public_id}[/bold cyan]", border_style="cyan"))
                    _print_profile(profile)
                    # Схеми
                    schemas = await client.list_schemas(public_id)
                    if schemas:
                        console.print("\n[bold]Опубліковані схеми:[/bold]")
                        _print_schemas(schemas)
                else:
                    # Свій бот
                    profile = await client.get_my_profile()
                    if not profile:
                        print_error("Не вдалося отримати профіль. Можливо, токен недійсний.")
                        return
                    console.print(Panel(f"[bold cyan]Мій профіль[/bold cyan]", border_style="cyan"))
                    _print_profile(profile)
                    # Схеми
                    schemas = await client.list_schemas(config.get_public_id())
                    if schemas:
                        console.print("\n[bold]Мої схеми:[/bold]")
                        _print_schemas(schemas)
                    # Гранти
                    grants = await client.list_grants()
                    if grants:
                        console.print("\n[bold]Видані гранти:[/bold]")
                        _print_grants(grants)
                    # Вебхуки
                    webhooks = await client.list_webhooks()
                    if webhooks:
                        console.print("\n[bold]Підписки на вебхуки:[/bold]")
                        _print_webhooks(webhooks)
        asyncio.run(_info())
    except Exception as e:
        print_error(f"Помилка: {e}")

def _print_profile(profile: dict):
    table = Table(box=box.ROUNDED, show_header=False)
    table.add_column("Поле", style="bold cyan")
    table.add_column("Значення")
    for key, value in profile.items():
        if key in ('createdAt', 'updatedAt'):
            continue
        if isinstance(value, list):
            value = ", ".join(value)
        table.add_row(key, str(value))
    console.print(table)

def _print_schemas(schemas: list):
    table = Table(title="Схеми", box=box.ROUNDED)
    table.add_column("Capability", style="cyan")
    table.add_column("Version")
    table.add_column("Updated")
    for s in schemas:
        table.add_row(s.get('capability', ''), s.get('schemaVersion', ''), str(s.get('updatedAt', '')))
    console.print(table)

def _print_grants(grants: list):
    table = Table(title="Гранти", box=box.ROUNDED)
    table.add_column("Grantee", style="cyan")
    table.add_column("Level")
    for g in grants:
        table.add_row(g.get('granteePublicId', ''), str(g.get('level', '')))
    console.print(table)

def _print_webhooks(webhooks: list):
    table = Table(title="Вебхуки", box=box.ROUNDED)
    table.add_column("ID", style="cyan")
    table.add_column("URL")
    table.add_column("Події")
    for w in webhooks:
        table.add_row(w.get('id', ''), w.get('url', ''), ", ".join(w.get('events', [])))
    console.print(table)

# ---------- presence ----------
@cli.group()
def presence():
    """Робота з присутністю в чатах."""
    pass

@presence.command('publish')
@click.option('--file', 'file_path', type=click.Path(exists=True), help='JSON-файл з масивом чатів')
@click.option('--chat', 'chat_data', multiple=True, help='Окремий чат у форматі chatId:level:data (data - JSON)')
@click.option('--auto-batch/--no-batch', default=True, help='Автоматично розбивати на батчі по 50')
def presence_publish(file_path, chat_data, auto_batch):
    """Опублікувати присутність у чатах."""
    chats = []
    if file_path:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                chats = data
            elif isinstance(data, dict) and 'chats' in data:
                chats = data['chats']
            else:
                print_error("Файл має містити масив об'єктів або об'єкт з полем 'chats'")
                return
    if chat_data:
        for item in chat_data:
            parts = item.split(':', 2)
            if len(parts) != 3:
                print_error(f"Невірний формат: {item}. Очікується chatId:level:data")
                return
            chat_id, level_str, data_str = parts
            try:
                level = int(level_str)
                data_obj = json.loads(data_str)
            except Exception as e:
                print_error(f"Помилка парсингу: {e}")
                return
            chats.append({"chatId": chat_id, "level": level, "data": data_obj})
    if not chats:
        print_error("Не вказано жодного чату.")
        return

    async def _publish():
        async with AsyncUBN() as client:
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
                task = progress.add_task("[cyan]Публікація...", total=len(chats))
                results = await client.publish_presence(chats, auto_batch=auto_batch)
                progress.update(task, completed=len(chats))
            # Показати результати
            total_updated = sum(r.get('updated', 0) for r in results)
            total_failed = sum(len(r.get('failed', [])) for r in results)
            print_success(f"Оновлено: {total_updated}, невдало: {total_failed}")
            if total_failed:
                for r in results:
                    for fail in r.get('failed', []):
                        print_warning(f"Чат {fail.get('chatId')}: {fail.get('error')}")
    asyncio.run(_publish())

@presence.command('get')
@click.argument('chat_ids', nargs=-1, required=True)
def presence_get(chat_ids):
    """Отримати присутність інших ботів у зазначених чатах."""
    if not chat_ids:
        print_error("Вкажіть хоча б один chatId")
        return
    async def _get():
        async with AsyncUBN() as client:
            result = await client.get_presence(list(chat_ids))
            if result.get('chats'):
                console.print("[bold]Присутність:[/bold]")
                for chat_id, entries in result['chats'].items():
                    console.print(f"\n[cyan]{chat_id}[/cyan]")
                    table = Table(box=box.ROUNDED)
                    table.add_column("Бот", style="cyan")
                    table.add_column("Рівень")
                    table.add_column("Дані")
                    for entry in entries:
                        table.add_row(
                            entry.get('botPublicId', ''),
                            str(entry.get('level', '')),
                            json.dumps(entry.get('data', {}), ensure_ascii=False)
                        )
                    console.print(table)
            if result.get('skipped') and result['skipped'].get('chatIds'):
                print_warning(f"Пропущено чати: {', '.join(result['skipped']['chatIds'])}")
    asyncio.run(_get())

# ---------- grants ----------
@cli.group()
def grants():
    """Керування партнерськими грантами."""
    pass

@grants.command('list')
def grants_list():
    """Показати список виданих грантів."""
    async def _list():
        async with AsyncUBN() as client:
            grants = await client.list_grants()
            if not grants:
                print_info("Грантів немає")
                return
            _print_grants(grants)
    asyncio.run(_list())

@grants.command('add')
@click.argument('grantee_public_id')
@click.argument('level', type=int)
def grants_add(grantee_public_id, level):
    """Видати грант партнеру."""
    async def _add():
        async with AsyncUBN() as client:
            result = await client.create_grant(grantee_public_id, level)
            print_success(f"Грант для {grantee_public_id} на рівень {level} створено")
    asyncio.run(_add())

@grants.command('remove')
@click.argument('grantee_public_id')
def grants_remove(grantee_public_id):
    """Відкликати грант."""
    async def _remove():
        async with AsyncUBN() as client:
            await client.revoke_grant(grantee_public_id)
            print_success(f"Грант для {grantee_public_id} відкликано")
    asyncio.run(_remove())

# ---------- webhooks ----------
@cli.group()
def webhooks():
    """Керування вебхуками."""
    pass

@webhooks.command('list')
def webhooks_list():
    """Список підписок."""
    async def _list():
        async with AsyncUBN() as client:
            wh = await client.list_webhooks()
            if not wh:
                print_info("Вебхуків немає")
                return
            _print_webhooks(wh)
    asyncio.run(_list())

@webhooks.command('add')
@click.argument('url')
@click.argument('events', nargs=-1, required=True)
def webhooks_add(url, events):
    """Додати вебхук. Події через пробіл (grant_received, grant_revoked, bot_verified)."""
    async def _add():
        async with AsyncUBN() as client:
            result = await client.create_webhook(url, list(events))
            print_success(f"Вебхук додано. ID: {result.get('webhookId')}")
            if 'secret' in result:
                console.print(f"[bold]Secret:[/bold] [yellow]{result['secret']}[/yellow] (збережіть!)")
    asyncio.run(_add())

@webhooks.command('remove')
@click.argument('webhook_id')
def webhooks_remove(webhook_id):
    """Видалити вебхук за ID."""
    async def _remove():
        async with AsyncUBN() as client:
            await client.delete_webhook(webhook_id)
            print_success(f"Вебхук {webhook_id} видалено")
    asyncio.run(_remove())

# ---------- schemas ----------
@cli.group()
def schemas():
    """Робота з контрактами схем."""
    pass

@schemas.command('list')
@click.argument('public_id', required=False)
def schemas_list(public_id):
    """Список схем (своїх або за public_id)."""
    async def _list():
        async with AsyncUBN() as client:
            pid = public_id or client.config.get_public_id()
            schemas = await client.list_schemas(pid)
            if not schemas:
                print_info("Схем не знайдено")
                return
            _print_schemas(schemas)
    asyncio.run(_list())

@schemas.command('publish')
@click.argument('capability')
@click.argument('version')
@click.argument('schema_file', type=click.Path(exists=True))
def schemas_publish(capability, version, schema_file):
    """Опублікувати схему з JSON-файлу."""
    try:
        with open(schema_file, 'r', encoding='utf-8') as f:
            schema = json.load(f)
    except Exception as e:
        print_error(f"Помилка читання файлу: {e}")
        return
    async def _publish():
        async with AsyncUBN() as client:
            result = await client.publish_schema(capability, version, schema)
            print_success(f"Схема '{capability}' v{version} опублікована")
    asyncio.run(_publish())

@schemas.command('get')
@click.argument('public_id')
@click.argument('capability')
def schemas_get(public_id, capability):
    """Отримати конкретну схему бота."""
    async def _get():
        async with AsyncUBN() as client:
            schema = await client.get_schema(public_id, capability)
            if schema:
                console.print_json(json.dumps(schema, ensure_ascii=False, indent=2))
            else:
                print_warning("Схему не знайдено")
    asyncio.run(_get())

# ---------- profile ----------
@cli.group()
def profile():
    """Керування профілем."""
    pass

@profile.command('show')
def profile_show():
    """Показати поточний профіль."""
    async def _show():
        async with AsyncUBN() as client:
            profile = await client.get_my_profile()
            if not profile:
                print_error("Не вдалося отримати профіль")
                return
            _print_profile(profile)
    asyncio.run(_show())

@profile.command('update')
@click.option('--bio', help='Короткий опис')
@click.option('--capabilities', help='Список можливостей через кому (наприклад, games,stickers)')
@click.option('--features', help='Список фіч через кому (presence,storage,...)')
def profile_update(bio, capabilities, features):
    """Оновити профіль."""
    caps = capabilities.split(',') if capabilities else None
    feats = features.split(',') if features else None
    async def _update():
        async with AsyncUBN() as client:
            result = await client.update_profile(bio=bio, capabilities=caps, features=feats)
            print_success("Профіль оновлено")
    asyncio.run(_update())

# ---------- discover ----------
@cli.command('discover')
@click.option('--capability', help='Фільтр за можливістю')
@click.option('--type', 'bot_type', help='Тип бота (telegram/service)')
@click.option('--feature', help='Фільтр за фічею')
@click.option('--features', help='Кілька фіч через кому')
def discover(capability, bot_type, feature, features):
    """Пошук ботів у каталозі."""
    async def _discover():
        async with AsyncUBN() as client:
            bots = await client.discover_bots(
                capability=capability,
                bot_type=bot_type,
                feature=feature,
                features=features,
            )
            if not bots:
                print_info("Ботів не знайдено")
                return
            table = Table(title="Знайдені боти", box=box.ROUNDED)
            table.add_column("Public ID", style="cyan")
            table.add_column("Назва")
            table.add_column("Тип")
            table.add_column("Можливості")
            table.add_column("Верифікований")
            for b in bots:
                table.add_row(
                    b.get('publicId', ''),
                    b.get('name', ''),
                    b.get('type', ''),
                    ", ".join(b.get('capabilities', [])),
                    "✅" if b.get('verified') else "❌"
                )
            console.print(table)
    asyncio.run(_discover())

# ---------- rotate-key ----------
@cli.command('rotate-key')
def rotate_key():
    """Перевипустити API-ключ."""
    async def _rotate():
        async with AsyncUBN() as client:
            result = await client.rotate_key()
            if result.get('ok'):
                print_success("Ключ перевипущено")
                console.print(f"[bold]Новий API Key:[/bold] [yellow]{result['apiKey']}[/yellow] (збережіть!)")
            else:
                print_error("Помилка перевипуску")
    asyncio.run(_rotate())

# ---------- health ----------
@cli.command('health')
def health():
    """Перевірка статусу сервера."""
    async def _health():
        async with AsyncUBN() as client:
            try:
                result = await client.health()
                if result.get('ok'):
                    print_success("Сервер працює")
                else:
                    print_warning("Сервер відповів, але з помилкою")
            except Exception as e:
                print_error(f"Не вдалося підключитися: {e}")
    asyncio.run(_health())

# ---------- flush ----------
@cli.command('flush')
def flush():
    """Примусово відправити накопичені в черзі запити."""
    async def _flush():
        async with AsyncUBN() as client:
            count = await client.flush_queued(silent=False)
            if count:
                print_success(f"Відправлено {count} запитів з черги")
            else:
                print_info("Черга порожня")
    asyncio.run(_flush())

# ---------- main ----------
def main():
    cli()

if __name__ == "__main__":
    main()