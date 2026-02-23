from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Класс настроек бота, загружаемых из переменных окружения или .env файла.
    """
    bot_token: str
    admin_id: int
    db_path: str = "bot_data.db"

    # Настройки AmneziaWG
    wg_interface: str = "awg0"
    wg_port: int = 51820
    server_pub_key: str = ""
    server_endpoint: str = ""
    dns_servers: str = "1.1.1.1, 8.8.8.8"
    vpn_ip_range: str = "10.8.0.0/24"

    # Параметры обфускации AmneziaWG
    jc: int = 4
    jmin: int = 40
    jmax: int = 70
    s1: int = 44
    s2: int = 148
    h1: int = 12345678
    h2: int = 87654321
    h3: int = 13572468
    h4: int = 24681357

    # Настройка загрузки из .env файла
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Создаем экземпляр настроек для использования в проекте
settings = Settings()
