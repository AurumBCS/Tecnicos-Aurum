# 📱 Portal Técnicos Aurum BC

Una aplicación simple que muestra toda la información importante de los técnicos de Aurum BC Security en un solo lugar.

---

## 🎯 ¿Qué es esto?

Es una página web que abre en el navegador y te muestra:
- 📊 Tus indicadores de calidad (KPIs)
- 📄 Los documentos que te faltan entregar
- 🚗 El vehículo que te asignaron
- 🏖️ Tus días de vacaciones
- 🛠️ Tu desempeño en reparaciones
- ✅ Tu cumplimiento de visitas
- ⭐ Medallas por satisfacción del cliente

Todo actualizado automáticamente desde Google Sheets.

---

## 🚀 Cómo usar

1. **Abre el archivo**: Abre `index.html` en tu navegador
2. **Inicia sesión**: Ingresa tu matrícula (y DNI si eres coordinador o JE)
3. **Mira tus datos**: Todo aparece automáticamente
4. **Refresca si quieres**: Hay un botón para actualizar manualmente

---

## 📊 Qué datos ves

### Indicadores de Calidad
Tus notas en:
- **ML-V** (Mantenimiento extra) - Verde bueno, naranja normal, rojo malo
- **MA+B** (Calidad en general)

### Resumen de Objetivos
Un círculo que muestra cuántos objetivos cumpliste de todos los que tenías.

### KPIs (Lo que importa)
- **%RM** - Porcentaje de reparaciones que resolviste en la primera visita
- **%Cumplimiento** - Porcentaje de visitas que completaste
- **Conversión** - Porcentaje de ventas extras que lograste
- **PPA** - Ingresos por producto propio
- **TU 20%** - Tu comisión del período

### Documentación Pendiente
Papers que aún no entregaste. Hay un botón para registro.

### Tu Coche Asignado
La matrícula del vehículo que usas.

### Vacaciones
Cuántos días ya usaste y cuántos te quedan.

### Dashboards Especiales
- **RM**: Análisis detallado de tus reparaciones repetidas
- **Cumplimiento**: Por qué no completaste algunas visitas
- **Medalia**: Satisfacción de clientes por zona

---

## 👥 Tipos de usuarios

### Técnico
- Ve solo sus propios datos
- Puede hacer refresh manual (solo algunos)

### Jefe de Equipo (JE)
- Ve sus datos + datos de su equipo
- Puede comparar desempeño del equipo

### Regional Manager (JR)
- Ve todos los equipos
- Ve ranking de todos los JE

---

## 🔄 Datos automáticos

Los datos se actualizan automáticamente:
- **Martes y Jueves** entre las 4pm y 11pm
- Cada **15 minutos** durante ese horario
- Siempre con los datos más recientes de Google Sheets

---

## 📁 Dónde vienen los datos

Todo viene de Google Sheets publicados como CSV:
- **Resumen App Claude** → Todos tus KPIs
- **CUADRANTE** → Autenticación (quién eres)
- **Documentación** → Papers pendientes
- **Flota** → Tu vehículo asignado
- **Vacaciones** → Días de descanso
- **RM** → Datos de reparaciones
- **Cumplimiento** → Visitas completadas
- **Medalia** → Satisfacción de clientes

---

## 💡 Cosas útiles

- **Sin instalación**: Solo abre la página
- **Sin internet lento**: Los datos se guardan localmente
- **Modo oscuro**: La página es fácil para los ojos
- **Responsive**: Funciona en celular y computadora
- **Rápido**: Todo carga en segundos

---

## ⚙️ Requisitos

- Un navegador web moderno (Chrome, Firefox, Safari, Edge)
- Internet para conectarse a Google Sheets la primera vez
- Tu matrícula y DNI (si aplica)

---

## 🐛 Si algo no funciona

1. Recarga la página (F5)
2. Borra el caché del navegador
3. Intenta en otro navegador
4. Verifica que los Google Sheets estén publicados

---

## 👨‍💼 Para administradores

La app está hecha con:
- **HTML/CSS/JS puro** - Sin librerías complicadas
- **Archivo único** - Todo en `index.html`
- **Google Sheets como base de datos** - Fácil de modificar
- **CSV directo** - Sin servidores complicados

Para cambiar datos, solo edita los Sheets de Google y publica como CSV.

---

## 🔧 Para Desarrolladores

### Arquitectura General

**Stack**: HTML/CSS/JavaScript vanilla (sin frameworks)  
**Punto de entrada**: `index.html` (archivo único)  
**Base de datos**: Google Sheets publicados como CSV  
**Autenticación**: Matrícula + DNI contra CSV de CUADRANTE

### Estructura de Datos

```javascript
// Datos cargados al iniciar
CURRENT_DATA = {
  tecnicos: [
    {
      id: "279300",
      nombre: "Alexander Xavier Hernandez",
      mlv: 8.08,        // Mantenimiento extra
      mab: 8.08,        // Calidad general
      pRM: 92.31,       // % Reparaciones resueltas 1ª visita
      pCum: 94.20,      // % Cumplimiento de visitas
      conv: 14.22,      // % Conversión
      ppa: 25,          // % PPA
      ventas: 256.00,   // Comisión
      // ... más campos
    }
  ]
}

// Datos de mantenimientos/reparaciones
RM_DATA = {
  "279300": [
    { nMant: "M12345", motivo: "Pilas bajas", motivoPost: "Falsas alarmas", territorial: "3305", repetido: 0 }
  ]
}

// Cumplimiento de visitas
CUM_DATA = {
  "279300": { total: 52, ok: 49, pct: 94, topRazones: [...] }
}

// Y más: DOCS_DATA, FLOTA_DATA, VACACIONES_DATA, MEDALIA_COORD_DATA
```

### Flujo de Carga de Datos

1. **Login**: Usuario ingresa matrícula + DNI
2. **Validación**: `doLogin()` valida contra AUTH_DATA
3. **Carga en paralelo**: 
   ```javascript
   Promise.all([
     loadSheets(),        // KPIs principales
     loadAuth(),          // Validación
     loadDocs(),          // Documentación
     loadVacaciones(),    // Vacaciones
     loadFlota(),         // Vehículos
     loadCumplimiento(),  // Visitas completadas
     loadRM()             // Reparaciones
   ])
   ```
4. **Renderizado**: `renderMain()` dibuja la UI con los datos
5. **Auto-refresh**: Cada 15 min (mar/jue 16:00-23:00)

### URLs de Google Sheets

```javascript
const SHEETS_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ2C6LbbD8...pub?output=csv";
const AUTH_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSvU7Aah...pub?output=csv";
const DOCS_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTsvNFJI2b...pub?output=csv";
const FLOTA_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQUPwezjgylsD...pub?output=csv";
const VACACIONES_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR9A0fhBk2Vi...pub?output=csv";
const CUMPLIMIENTO_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSnEsNP3Xdt...pub?output=csv";
const RM_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRVDFiOmr7q76bi...pub?output=csv";
const MEDALIA_COORD_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTIbmLaEbAJ...pub?output=csv";
```

### Funciones Principales

**Autenticación**
- `doLogin()` - Valida credenciales y carga datos
- `doLogout()` - Limpia sesión
- `loadAuth()` - Lee CUADRANTE publicado como CSV

**Renderizado**
- `renderMain(tec)` - Dibuja panel del técnico
- `renderEquipoPanel(jeId)` - Panel del Jefe de Equipo
- `renderJRPanel()` - Panel del Regional Manager

**Dashboards**
- `_openRMDash(tecId)` - Dashboard de reparaciones
- `showCumDash(tecId)` - Dashboard de cumplimiento
- `renderMedialiaCoord()` - Medalia por territorio

**Carga de datos**
- `loadSheets()` - CSV principal (KPIs)
- `loadAuth()` - Autenticación y validación de usuarios
- `loadDocs()` - Documentación pendiente
- `loadFlota()` - Vehículos asignados
- `loadVacaciones()` - Días de vacaciones
- `loadCumplimiento()` - Visitas completadas
- `loadRM()` - Datos de reparaciones
- `loadMedialiaCoord()` - Medallas por territorio/coordinador

### Estructura del CSV Principal

El CSV del "Resumen App Claude" tiene columnas como:
```
MATRICULA | Técnico | Jerárquico | pRM | pCum | conv | ppa | mlv | mab | ventas | palito | rm | ...
279300    | Alexander | 239831  | 92.31 | 94.20 | 14.22 | 25 | 8.08 | 8.08 | 256.00 | 39 | 3 | ...
```

### Estructura de Roles

```javascript
CURRENT_USER_TYPE = 'tecnico' | 'je' | 'jr'

// Técnico: ve solo sus datos
// JE (Jefe de Equipo): ve su equipo + datos de su equipo
// JR (Regional Manager): ve todos los JE y sus equipos

JERARQUIA = {
  'JR9426': ['239831', '286800', ...],      // JR con sus JE
  '239831': ['296625', '336070', ...]       // JE con sus técnicos
}
```

### Parseo de CSV

```javascript
function parseCSV(text) {
  // Maneja CSV con comillas y saltos de línea dentro de campos
  // Retorna array de objetos con headers como keys
  return rows.map(row => ({
    'MATRICULA': row[0],
    'Técnico': row[1],
    ...
  }))
}
```

### Auto-Refresh

```javascript
function startAutoRefresh() {
  const ahora = new Date();
  const dia = ahora.getDay();        // 0=dom, 2=mar, 4=jue
  const hora = ahora.getHours();
  
  // Solo mar/jue entre 16:00-23:00
  if((dia===2 || dia===4) && hora>=16 && hora<23) {
    setInterval(() => {
      loadSheets(); loadAuth(); loadCumplimiento(); loadRM(); ...
    }, 15*60*1000)  // 15 minutos
  }
}
```

### Agregar Cambios

1. **No tocar GitHub sin permiso** - Prueba localmente primero
2. **Cambios en datos**: Edita el Google Sheet → publica como CSV
3. **Cambios en código**: Edita `index.html` localmente
4. **Agregar un nuevo indicador**:
   - Agrega URL de Google Sheet en línea 484+
   - Crea función `loadNuevoDato()` 
   - Agrega la promesa a `doLogin()`
   - Renderiza en `renderMain()`
5. **Testing**: Abre en navegador y valida con F12 (consola)

### Despliegue

Los cambios se suben a GitHub y se sirven desde:
```
https://github.com/AurumBCS/Tecnicos-Aurum
```

Workflow:
1. Prueba en local
2. Commit a GitHub
3. Los usuarios abren `index.html` directamente (carga siempre la última versión)

### Limitaciones y Notas

- **Sin backend**: Todo es front-end (ventaja: simple, desventaja: sin lógica compleja)
- **CSV only**: Los datos siempre vienen como CSV desde Google Sheets
- **Sin caché persistente**: Los datos se cargan cada vez (con fallback local)
- **Números europeos**: El CSV usa comas para decimales y puntos para miles (parseNum/parseMoney)
- **Case insensitive**: Las matrículas se normalizan a mayúsculas

### Debug en Consola

```javascript
// Ver datos actuales
console.log(CURRENT_DATA.tecnicos)
console.log(RM_DATA)
console.log(CUM_DATA)

// Ver usuario actual
console.log(CURRENT_USER_TYPE)
console.log(CURRENT_TEC)

// Forzar recarga
doLogout()
// Luego login de nuevo
```

---

**Versión**: 1.0.2 | **Última actualización**: Mayo 2026
