from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Класс настроек бота, загружаемых из переменных окружения или .env файла.
    """
    bot_token: str
    admin_id: int
    db_path: str = "bot_data.db"
    
    # Ключ для шифрования приватных ключей VPN (Fernet)
    # Можно сгенерировать через: cryptography.fernet.Fernet.generate_key()
    encryption_key: SecretStr | None = Field(default=None)

    # Настройки AmneziaWG
    wg_interface: str = "awg0"
    wg_container_name: str = ""  # Имя Docker-контейнера с AmneziaWG (если пусто — вызовы напрямую)
    wg_port: int = 51820
    server_pub_key: str = ""
    server_endpoint: str = ""
    dns_servers: str = "1.1.1.1, 8.8.8.8"
    vpn_ip_range: str = "10.8.0.0/24"
    max_profiles_per_user: int = 3

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

    # Дополнительные параметры AmneziaWG (расширенная обфускация)
    # 0 = не включать в клиентский конфиг (стандартный AWG их не требует)
    # Необходимы для сборок AWG-ядра с расширенной обфускацией (S3/S4/I1)
    s3: int = 0
    s4: int = 0
    i1: int = 0

    # Логирование
    log_level: str = "INFO"   # DEBUG | INFO | WARNING | ERROR
    log_path: str = "logs"    # директория для файлов логов

    # FSM Storage (опционально — Redis для production)
    # Если не задан, используется MemoryStorage (данные теряются при рестарте)
    redis_url: str | None = None  # пример: redis://localhost:6379/0

    # Настройка загрузки из .env файла
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Создаем экземпляр настроек для использования в проекте
settings = Settings()  # type: ignore[call-arg]
