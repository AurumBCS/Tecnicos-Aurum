# Imagen de contenedor para el Lambda de la automatizacion OFS.
#
# Se parte de la imagen oficial de Playwright (trae Chromium y TODAS sus
# dependencias del sistema ya instaladas) en vez de una imagen base de
# Lambda (Amazon Linux), porque `playwright install --with-deps` -- la
# forma soportada de instalar esas dependencias -- solo funciona en
# Debian/Ubuntu, no en Amazon Linux.
#
# La version de esta imagen (v1.62.0) y la de "playwright" en
# requirements.txt DEBEN coincidir exactamente: los navegadores quedan
# cacheados por version, y si no coinciden Playwright no encuentra el
# ejecutable de Chromium en tiempo de ejecucion. Si algun dia se sube la
# version en requirements.txt, hay que subir tambien el tag de aqui.
FROM mcr.microsoft.com/playwright/python:v1.62.0-jammy

# Esta imagen no es una de las imagenes base oficiales de Lambda
# (public.ecr.aws/lambda/*), asi que para que el contenedor hable el
# protocolo de invocacion de Lambda hace falta instalar el Runtime
# Interface Client manualmente.
RUN pip install --no-cache-dir awslambdaric

WORKDIR /var/task

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY comun_ofs.py tomar_capturas.py enviar_correo_matutino.py descargar_ruta_y_subir.py lambda_handler.py ./

ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["lambda_handler.handler"]
