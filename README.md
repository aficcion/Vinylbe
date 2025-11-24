# 🎵 Vinylbe - Vinyl Recommendation Platform

Una plataforma de recomendaciones de vinilos que integra Last.fm, Discogs y eBay para ayudarte a descubrir y comprar música en vinilo.

![Status](https://img.shields.io/badge/status-ready%20to%20deploy-green)
![Python](https://img.shields.io/badge/python-3.9+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-00a393)

## ✨ Características

- 🎧 **Integración con Last.fm**: Conecta tu cuenta y obtén recomendaciones basadas en tu historial
- 💿 **Búsqueda en Discogs**: Encuentra información detallada de álbumes y precios
- 💰 **Precios de eBay**: Compara precios en tiempo real
- ⭐ **Favoritos y Colección**: Marca tus álbumes favoritos y los que ya tienes
- 🔍 **Búsqueda de Artistas**: Busca y añade artistas manualmente
- 📊 **Recomendaciones Personalizadas**: Algoritmo que combina tus gustos con disponibilidad

## 🏗️ Arquitectura

Vinylbe está construido como una **arquitectura de microservicios**:

```
┌─────────────────────────────────────────────────────────┐
│                     API Gateway (5000)                   │
│              Frontend + Coordinación de Servicios        │
└─────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼──────┐   ┌────────▼────────┐   ┌─────▼──────┐
│   Discogs    │   │   Recommender   │   │  Last.fm   │
│  Service     │   │    Service      │   │  Service   │
│   (3001)     │   │     (3002)      │   │   (3004)   │
└──────────────┘   └─────────────────┘   └────────────┘
                           │
                   ┌───────▼────────┐
                   │    Pricing     │
                   │    Service     │
                   │     (3003)     │
                   └────────────────┘
```

### Servicios

- **Gateway** (puerto 5000): API principal y frontend estático
- **Discogs Service** (puerto 3001): Búsqueda de álbumes y artistas
- **Recommender Service** (puerto 3002): Generación de recomendaciones
- **Pricing Service** (puerto 3003): Precios de eBay y tiendas locales
- **Last.fm Service** (puerto 3004): Autenticación y datos de usuario

## 🚀 Inicio Rápido

### Requisitos Previos

- Python 3.9+
- Cuentas y API keys de:
  - [Discogs](https://www.discogs.com/settings/developers)
  - [Last.fm](https://www.last.fm/api/account/create)
  - [eBay](https://developer.ebay.com/)

### Instalación Local

1. **Clonar el repositorio**
   ```bash
   git clone https://github.com/TU_USUARIO/vinylbe.git
   cd vinylbe
   ```

2. **Crear entorno virtual**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # En Windows: .venv\Scripts\activate
   ```

3. **Instalar dependencias**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurar variables de entorno**
   ```bash
   cp .env.example .env
   # Edita .env con tus API keys
   ```

5. **Iniciar todos los servicios**
   ```bash
   python start_services.py
   ```

6. **Abrir en el navegador**
   ```
   http://localhost:5000
   ```

## 📦 Despliegue en Producción

### Opción Recomendada: Railway

Railway es la forma más fácil de desplegar Vinylbe:

```bash
# 1. Verificar que todo está listo
./check_deploy.sh

# 2. Preparar para despliegue (interactivo)
./prepare_deploy.sh

# 3. Seguir la guía de Railway
# Ver INICIO_RAPIDO.md para instrucciones detalladas
```

### Otras Opciones

- **Render**: Plan gratuito, ver `render.yaml`
- **Fly.io**: Excelente para microservicios, ver `fly.toml`
- **Docker**: Usa `docker-compose.yml` para despliegue en VPS
- **Replit**: Para prototipos rápidos

📖 **Guía completa**: Ver [GUIA_DESPLIEGUE.md](./GUIA_DESPLIEGUE.md)

## 🛠️ Desarrollo

### Estructura del Proyecto

```
vinylbe/
├── gateway/              # API Gateway y frontend
│   ├── main.py          # FastAPI app principal
│   ├── db.py            # Capa de persistencia SQLite
│   ├── db_utils.py      # Utilidades de base de datos
│   └── static/          # Frontend (HTML/CSS/JS)
├── services/            # Microservicios
│   ├── discogs/        # Servicio de Discogs
│   ├── recommender/    # Motor de recomendaciones
│   ├── pricing/        # Servicio de precios
│   └── lastfm/         # Servicio de Last.fm
├── libs/               # Librerías compartidas
├── db_explorer/        # Explorador de base de datos
├── vinylbe.db          # Base de datos SQLite
└── start_services.py   # Script de inicio
```

### Scripts Útiles

```bash
# Verificar configuración antes de desplegar
./check_deploy.sh

# Preparar para despliegue (Git + push)
./prepare_deploy.sh

# Iniciar todos los servicios
python start_services.py

# Iniciar servicios para producción
python start_services_prod.py

# Explorar base de datos
streamlit run db_explorer/app.py
```

### Testing

```bash
# Test de endpoints
python test_endpoints.py

# Test de autenticación eBay
python test_ebay_auth.py

# Debug de Discogs
python debug_discogs.py
```

## 📊 Base de Datos

Vinylbe usa **SQLite** para persistencia:

- `users`: Usuarios (Google OAuth + Last.fm)
- `user_profile_lastfm`: Perfiles de Last.fm
- `user_selected_artists`: Artistas seleccionados por usuario
- `user_recommendations`: Recomendaciones personalizadas

Para explorar la base de datos:
```bash
streamlit run db_explorer/app.py
```

## 🔐 Variables de Entorno

Crea un archivo `.env` con:

```env
# Discogs
DISCOGS_API_KEY=tu_clave
DISCOGS_API_SECRET=tu_secreto

# Last.fm
LASTFM_API_KEY=tu_clave
LASTFM_API_SECRET=tu_secreto

# eBay
EBAY_APP_ID=tu_app_id
EBAY_CERT_ID=tu_cert_id

# URLs de servicios (opcional, usa defaults)
DISCOGS_SERVICE_URL=http://127.0.0.1:3001
RECOMMENDER_SERVICE_URL=http://127.0.0.1:3002
PRICING_SERVICE_URL=http://127.0.0.1:3003
LASTFM_SERVICE_URL=http://127.0.0.1:3004
```

## 📚 Documentación

- [GUIA_DESPLIEGUE.md](./GUIA_DESPLIEGUE.md) - Guía completa de despliegue
- [INICIO_RAPIDO.md](./INICIO_RAPIDO.md) - Tutorial Railway paso a paso
- [ESTADO_DESPLIEGUE.md](./ESTADO_DESPLIEGUE.md) - Estado actual del proyecto
- [GUIA_EXPLORACION_DB.md](./GUIA_EXPLORACION_DB.md) - Cómo usar el explorador de DB
- [MIGRACION_SQLITE.md](./MIGRACION_SQLITE.md) - Migración a SQLite
- [replit.md](./replit.md) - Configuración de Replit

## 🤝 Contribuir

Las contribuciones son bienvenidas! Por favor:

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📝 Licencia

Este proyecto es de código abierto y está disponible bajo la licencia MIT.

## 🙏 Agradecimientos

- [Discogs](https://www.discogs.com/) - Base de datos de música
- [Last.fm](https://www.last.fm/) - Scrobbling y datos de usuario
- [eBay](https://www.ebay.com/) - Precios de mercado
- [FastAPI](https://fastapi.tiangolo.com/) - Framework web
- [Railway](https://railway.app/) - Plataforma de despliegue

## 📞 Soporte

¿Problemas o preguntas?

1. Revisa la [documentación](./GUIA_DESPLIEGUE.md)
2. Ejecuta `./check_deploy.sh` para diagnosticar
3. Abre un [issue](https://github.com/TU_USUARIO/vinylbe/issues)

---

Hecho con ❤️ y 🎵 para los amantes del vinilo
