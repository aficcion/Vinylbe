FROM python:3.11-slim

# Establecer directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema necesarias
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements primero para aprovechar cache de Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Crear directorio para la base de datos si no existe
RUN mkdir -p /app/data

# Exponer puerto del gateway
EXPOSE 5000

# Variables de entorno por defecto
ENV PORT=5000
ENV PYTHONUNBUFFERED=1

# Comando para iniciar todos los servicios
CMD ["python", "start_services.py"]
