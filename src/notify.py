# Notification: after a job finishes, send its status and final results to
# the targets defined in the notify field of the job file
# (email / webhook / kafka / rabbitmq).
# Each target is sent independently; a failed notification is logged and
# does not affect the job result.
import json
import logging
import smtplib
import urllib.request
from email.mime.text import MIMEText

from src.util import render

logger = logging.getLogger("executor")


def _as_text(value) -> str:
    """Stringify a rendered template value; dicts/lists are converted to json"""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def notify(destinations: list, job_vars: dict, payload: dict):
    """Send the job result payload to every notify destination.
    Config values support ${var} / ${secret.xxx} references plus the built-in
    variables: ${status}, ${job_id}, ${job_name}, ${result} (json string)"""
    ctx = dict(job_vars)
    ctx.update({
        "status": payload["status"],
        "job_id": payload["job_id"],
        "job_name": payload["job_name"],
        "error": payload.get("error") or "",
        "result": json.dumps(payload, ensure_ascii=False, default=str),
    })
    for dest in destinations:
        try:
            dest = dict(dest)
            dest.pop("on_failure", None)
            kind, cfg = next(iter(dest.items()))
            cfg = render(cfg, ctx)
            if kind == "email":
                _send_email(cfg)
            elif kind == "webhook":
                _send_webhook(cfg, payload)
            elif kind == "kafka":
                _send_kafka(cfg, payload)
            elif kind == "rabbitmq":
                _send_rabbitmq(cfg, payload)
            else:
                logger.warning("unknown notify type: %s", dest)
        except Exception as e:
            logger.error("notify failed (%s): %s", dest, e)


def _send_email(cfg: dict):
    to = cfg["to"] if isinstance(cfg["to"], list) else [cfg["to"]]
    msg = MIMEText(_as_text(cfg["body"]), "plain", "utf-8")
    msg["Subject"] = _as_text(cfg["subject"])
    msg["From"] = cfg["from"]
    msg["To"] = ", ".join(to)
    port = int(cfg.get("smtp_port", 465))
    if cfg.get("smtp_ssl", True):
        server = smtplib.SMTP_SSL(cfg["smtp_host"], port, timeout=10)
    else:
        server = smtplib.SMTP(cfg["smtp_host"], port, timeout=10)
    with server:
        if cfg.get("smtp_user"):
            server.login(cfg["smtp_user"], cfg.get("smtp_password") or "")
        server.sendmail(cfg["from"], to, msg.as_string())
    logger.info("email notification sent to %s", to)


def _send_webhook(cfg: dict, payload: dict):
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    req = urllib.request.Request(
        cfg["url"],
        data=body,
        headers={"Content-Type": "application/json", **(cfg.get("headers") or {})},
        method=str(cfg.get("method", "POST")).upper(),
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        logger.info("webhook notification sent to %s (status %s)",
                    cfg["url"], resp.status)


def _send_kafka(cfg: dict, payload: dict):
    from kafka import KafkaProducer

    brokers = cfg["broker"] if isinstance(cfg["broker"], list) else [cfg["broker"]]
    producer = KafkaProducer(bootstrap_servers=brokers)
    try:
        message = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        producer.send(cfg["topic"], message)
        producer.flush()
    finally:
        producer.close()
    logger.info("kafka notification sent to topic %s", cfg["topic"])


def _send_rabbitmq(cfg: dict, payload: dict):
    import pika

    kwargs = {
        "host": cfg.get("host", "localhost"),
        "port": int(cfg.get("port", 5672)),
        "virtual_host": cfg.get("virtual_host", "/"),
    }
    if cfg.get("username"):
        kwargs["credentials"] = pika.PlainCredentials(
            cfg["username"], cfg.get("password") or ""
        )
    conn = pika.BlockingConnection(pika.ConnectionParameters(**kwargs))
    try:
        channel = conn.channel()
        channel.queue_declare(queue=cfg["queue"], durable=True)
        channel.basic_publish(
            exchange="",
            routing_key=cfg["queue"],
            body=json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
        )
    finally:
        conn.close()
    logger.info("rabbitmq notification sent to queue %s", cfg["queue"])
