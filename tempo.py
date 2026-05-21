from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


try:
    BRASILIA_TZ = ZoneInfo("America/Sao_Paulo")
except ZoneInfoNotFoundError:
    BRASILIA_TZ = timezone(timedelta(hours=-3), name="America/Sao_Paulo")


def agora_brasilia():
    return datetime.now(BRASILIA_TZ).replace(tzinfo=None)


def hoje_brasilia():
    return agora_brasilia().date()


def formatar_data_hora_brasilia(valor):
    if not valor:
        return ""

    if valor.tzinfo is not None:
        valor = valor.astimezone(BRASILIA_TZ)

    return valor.strftime("%d/%m/%Y %H:%M")
