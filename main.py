#!/usr/bin/env python3
"""
Team Assistant - AI-powered team assistant with GitLab, YouGile and Telegram integration
"""

import click
import uvicorn
from src.config import settings


@click.command()
@click.option('--host', default=settings.HOST, help='Host to bind to')
@click.option('--port', default=settings.PORT, help='Port to bind to')
@click.option('--reload', is_flag=True, help='Enable auto-reload for development')
def cli(host: str, port: int, reload: bool):
    """Start the Team Assistant server"""
    click.echo("="*60)
    click.echo("Team Assistant - Starting...")
    click.echo("="*60)
    click.echo(f"LLM Provider: {settings.LLM_PROVIDER}")
    click.echo(f"Outline: {'configured' if settings.validate_outline_config() else 'not configured'}")
    click.echo(f"GitLab: {'configured' if settings.validate_gitlab_config() else 'not configured'}")
    click.echo(f"YouGile: {'configured' if settings.validate_yougile_config() else 'not configured'}")
    click.echo(f"Telegram: {'configured' if settings.validate_telegram_config() else 'not configured'}")
    click.echo(f"Server: http://{host}:{port}")
    click.echo("="*60)
    
    uvicorn.run(
        "src.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level=settings.LOG_LEVEL.lower()
    )


if __name__ == '__main__':
    cli()
