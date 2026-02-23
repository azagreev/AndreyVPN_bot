from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Класс настроек бота, загружаемых из переменных окружения или .env файла.
    """
    bot_token: str
    admin_id: int
    db_path: str = "bot_data.db"

    # Настройка загрузки из .env файла
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Создаем экземпляр настроек для использования в проекте
settings = Settings()
