# Versiones del Script Google Apps Script

Este archivo documenta qué deployment ID corresponde a cada versión estable del script.

## v1.0.1-stable

**Fecha:** 2026-05-22
**Archivo local:** `google-apps-script-final.gs`
**Deployment ID:** `AKfycbzbIz1I7pjuPJ-7FerCeYuJAR2D6Il5Ah5d5_4v7f9Z5rGjDOXV1QCgGKLpe-gdtlgD`
**Endpoints funcionando:**
- Auth: JSON ✓ (117 matrículas cargadas)
- CSV (datos técnicos): CSV ✓ (101 técnicos)
- Docs: CSV ✓ (66 documentos)
- Flota: CSV ✓ (105 vehículos)
- Vacaciones: CSV ✓ (93 técnicos)
- Medalia: CSV ✓
- Medalia Coordinadores: CSV ✓
- Cumplimiento: CSV ✓
- RM: CSV ✓

**Cambios en esta versión:**
- ✓ Auth endpoint ahora lee desde CUADRANTE publicado como CSV
- ✓ parseCSV() parsea correctamente valores entre comillas
- ✓ Headers sin acentos en CUADRANTE (Jerarquia, Matricula, Tecnico, Direccion, DNI)
- ✓ Logs detallados en servirAuth() para debugging
- ✓ Todos los endpoints devuelven CSV sin errores CORS

**Comit Git:** pendiente
**Tag Git:** `v1.0.1-stable`

---

## v1.0.0-stable (Anterior)

**Fecha:** 2026-05-21
**Archivo local:** `google-apps-script-v1.0.0-stable.gs`
**Deployment ID:** `AKfycbx748de8faod6OY4K8DNp7PwdLjsYmo96W-4AzyMjF6nc0YCJq0PKXM1fTJ17dXMUF6`
**Endpoints funcionando:**
- Auth: JSON ✓
- CSV (datos técnicos): CSV ✓
- Docs: CSV ✓
- Flota: CSV ✓
- Vacaciones: CSV ✓
- Medalia: CSV ✓
- Medalia Coordinadores: CSV ✓
- Cumplimiento: CSV ✓
- RM: CSV ✓

**Comit Git:** `5c2e1d0`
**Tag Git:** `v1.0.0-stable`

---

## Cómo agregar cambios sin dañar la versión estable:

1. **En Google Apps Script:** Crea un NUEVO deployment (no modifiques el anterior)
2. **En index.html:** Actualiza el deployment ID en una rama `mejoras` o `feature/*`
3. **Prueba:** Verifica que todo funcione en el preview
4. **Si funciona:** Merge a main y crea un nuevo tag (v1.1.0, v1.2.0, etc.)
5. **Respaldo:** Copia el script a `google-apps-script-v1.1.0.gs` y commitea

## Si algo se rompe:

1. Ve a GitHub → Releases y descarga el script de la versión estable
2. O usa: `git checkout v1.0.0-stable -- google-apps-script-v1.0.0-stable.gs`
3. Copia su contenido a Google Apps Script editor
4. Usa el deployment ID original de esa versión en index.html
