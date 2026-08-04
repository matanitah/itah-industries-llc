import uvicorn

from spark_gateway.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "spark_gateway.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
