from dataclasses import dataclass
from email.message import EmailMessage
import logging
import os
import smtplib

from flask import current_app, has_app_context


ENV_ALIASES = {
    "MAIL_ENABLED": ("MAIL_ENABLED", "EMAIL_ENABLED", "SMTP_ENABLED"),
    "MAIL_SERVER": ("MAIL_SERVER", "SMTP_HOST", "SMTP_SERVER", "EMAIL_HOST", "EMAIL_SERVER"),
    "MAIL_PORT": ("MAIL_PORT", "SMTP_PORT", "EMAIL_PORT"),
    "MAIL_USERNAME": ("MAIL_USERNAME", "SMTP_USER", "SMTP_USERNAME", "EMAIL_USER", "EMAIL_USERNAME"),
    "MAIL_PASSWORD": ("MAIL_PASSWORD", "SMTP_PASSWORD", "SMTP_PASS", "EMAIL_PASSWORD"),
    "MAIL_DEFAULT_SENDER": ("MAIL_DEFAULT_SENDER", "SMTP_FROM", "EMAIL_FROM", "DEFAULT_FROM_EMAIL"),
    "MAIL_USE_TLS": ("MAIL_USE_TLS", "SMTP_USE_TLS", "EMAIL_USE_TLS"),
    "MAIL_USE_SSL": ("MAIL_USE_SSL", "SMTP_USE_SSL", "EMAIL_USE_SSL"),
}

CONFIG_OBRIGATORIA = (
    "MAIL_SERVER",
    "MAIL_PORT",
    "MAIL_USERNAME",
    "MAIL_PASSWORD",
    "MAIL_DEFAULT_SENDER",
)


@dataclass
class EmailConfig:
    enabled: bool
    server: str | None
    port: int | None
    username: str | None
    password: str | None
    default_sender: str | None
    use_tls: bool
    use_ssl: bool
    missing: tuple[str, ...]

    @property
    def configurado(self):
        return not self.missing


@dataclass
class EmailSendResult:
    enviado: bool
    erro: str | None = None
    faltando_config: tuple[str, ...] = ()
    desativado: bool = False


def _logger():
    if has_app_context():
        return current_app.logger
    return logging.getLogger(__name__)


def _ambiente():
    return os.environ.get("APP_ENV", "production").strip().lower() or "production"


def ambiente_desenvolvimento_ou_teste():
    return _ambiente() in {"development", "test"}


def parse_bool(valor, default=False):
    if valor is None or str(valor).strip() == "":
        return default
    return str(valor).strip().lower() in {"1", "true", "yes", "on"}


def mail_env(chave):
    for alias in ENV_ALIASES.get(chave, (chave,)):
        valor = os.environ.get(alias)
        if valor is not None and str(valor).strip() != "":
            return valor.strip()
    return None


def carregar_config_email(app):
    for chave in ENV_ALIASES:
        valor = mail_env(chave)
        if valor is not None:
            app.config[chave] = valor

    app.config.setdefault("MAIL_ENABLED", "true")
    app.config.setdefault("MAIL_USE_TLS", "true")
    app.config.setdefault("MAIL_USE_SSL", "false")


def configuracao_email():
    valores = {
        chave: (
            current_app.config.get(chave)
            if has_app_context() and current_app.config.get(chave) not in (None, "")
            else mail_env(chave)
        )
        for chave in ENV_ALIASES
    }

    missing = tuple(chave for chave in CONFIG_OBRIGATORIA if not valores.get(chave))

    porta = None
    if valores.get("MAIL_PORT"):
        try:
            porta = int(valores["MAIL_PORT"])
        except (TypeError, ValueError):
            missing = tuple(dict.fromkeys((*missing, "MAIL_PORT")))

    use_ssl = parse_bool(valores.get("MAIL_USE_SSL"), default=False)
    use_tls = parse_bool(valores.get("MAIL_USE_TLS"), default=not use_ssl)
    if use_ssl:
        use_tls = False

    return EmailConfig(
        enabled=parse_bool(valores.get("MAIL_ENABLED"), default=True),
        server=valores.get("MAIL_SERVER"),
        port=porta,
        username=valores.get("MAIL_USERNAME"),
        password=valores.get("MAIL_PASSWORD"),
        default_sender=valores.get("MAIL_DEFAULT_SENDER"),
        use_tls=use_tls,
        use_ssl=use_ssl,
        missing=missing,
    )


def smtp_configurado():
    config = configuracao_email()
    return config.enabled and config.configurado


def _erro_config_ausente(missing):
    return "Configuracao SMTP ausente ou invalida. Variaveis faltando: " + ", ".join(missing)


def enviar_email(destinatarios, assunto, texto, html=None):
    emails = list(dict.fromkeys(
        (email or "").strip().lower()
        for email in destinatarios
        if (email or "").strip()
    ))
    if not emails:
        return EmailSendResult(False, erro="Nenhum destinatario informado.")

    config = configuracao_email()
    if not config.enabled:
        _logger().info("email_nao_enviado motivo=mail_desativado")
        return EmailSendResult(False, erro="Envio de email desativado.", desativado=True)

    if not config.configurado:
        erro = _erro_config_ausente(config.missing)
        log = _logger()
        if ambiente_desenvolvimento_ou_teste():
            log.warning("email_nao_enviado motivo=configuracao_ausente faltando=%s", ",".join(config.missing))
        else:
            log.error("email_nao_enviado motivo=configuracao_ausente faltando=%s", ",".join(config.missing))
        return EmailSendResult(False, erro=erro, faltando_config=config.missing)

    mensagem = EmailMessage()
    mensagem["Subject"] = assunto
    mensagem["From"] = config.default_sender
    mensagem["To"] = ", ".join(emails)
    mensagem.set_content(texto)
    if html:
        mensagem.add_alternative(html, subtype="html")

    try:
        smtp_cls = smtplib.SMTP_SSL if config.use_ssl else smtplib.SMTP
        with smtp_cls(config.server, config.port) as servidor:
            if config.use_tls:
                servidor.starttls()
            servidor.login(config.username, config.password)
            servidor.send_message(mensagem)
        return EmailSendResult(True)
    except Exception as erro:
        _logger().error(
            "email_nao_enviado motivo=erro_smtp tipo=%s",
            type(erro).__name__,
        )
        return EmailSendResult(False, erro=f"Falha SMTP: {type(erro).__name__}")


def corpo_codigo_recuperacao(codigo):
    return (
        "Ola!\n\n"
        "Recebemos uma solicitacao para redefinir sua senha no sistema da "
        "Prospera Producoes.\n\n"
        "Seu codigo de verificacao e:\n\n"
        f"{codigo}\n\n"
        "Este codigo expira em 10 minutos.\n\n"
        "Se voce nao solicitou essa alteracao, ignore este e-mail.\n\n"
        "Atenciosamente,\n"
        "Prospera Producoes"
    )


def corpo_codigo_cadastro(codigo):
    return (
        "Ola!\n\n"
        "Use o codigo abaixo para concluir seu cadastro no sistema da "
        "Prospera Producoes:\n\n"
        f"{codigo}\n\n"
        "Este codigo expira em 15 minutos.\n\n"
        "Se voce nao solicitou esse cadastro, ignore este e-mail.\n\n"
        "Atenciosamente,\n"
        "Prospera Producoes"
    )


def enviar_codigo_recuperacao(destinatario, codigo):
    return enviar_email(
        [destinatario],
        "Codigo de recuperacao de senha - Prospera Producoes",
        corpo_codigo_recuperacao(codigo),
    )


def enviar_codigo_cadastro(destinatario, codigo):
    return enviar_email(
        [destinatario],
        "Codigo de verificacao - Sistema Prospera Producoes",
        corpo_codigo_cadastro(codigo),
    )
