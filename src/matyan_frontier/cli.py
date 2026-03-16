import click


@click.group()
def main() -> None:
    """Matyan Frontier CLI."""


@main.command()
@click.option("--host", default="0.0.0.0", help="Server host")
@click.option("--port", default=53801, help="Server port")
def start(host: str, port: int) -> None:
    """Start the Frontier ingestion gateway."""
    import uvicorn  # noqa: PLC0415

    from matyan_frontier.config import SETTINGS  # noqa: PLC0415

    uvicorn.run(
        "matyan_frontier.app:app",
        host=host,
        port=port,
        workers=1,
        log_level=SETTINGS.log_level.lower(),
    )


if __name__ == "__main__":  # pragma: no cover
    main()
