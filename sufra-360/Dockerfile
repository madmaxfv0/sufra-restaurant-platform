# SUFRA 360 - the guest-facing 3D restaurant. Holds no data of its own:
# everything operational is read from and written to SUFRA OS (SUFRA_OS_BASE).
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv/360
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY venue ./venue
COPY assets ./assets
COPY static ./static
EXPOSE 8013
# empty host = every interface, IPv4 and IPv6 ("::" alone answers IPv6 only)
CMD ["uvicorn", "app.main:app", "--host", "", "--port", "8013", "--proxy-headers", "--forwarded-allow-ips", "*"]
