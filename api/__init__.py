"""
Paquete de la Cloud API.

Existe para que `import api.index` funcione en el runtime de Vercel.
Sin este archivo, `api` no es un paquete: en local no se nota porque
uvicorn se lanza desde la raiz del proyecto y el directorio actual
entra en sys.path, pero Vercel importa el modulo de la funcion por su
ruta y `import api._env` —la primera linea de index.py— falla con
ModuleNotFoundError, que es lo que produce FUNCTION_INVOCATION_FAILED.
"""
