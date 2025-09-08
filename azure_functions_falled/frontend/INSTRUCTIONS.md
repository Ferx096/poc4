# VS Code para la Web - Azure AI Foundry

Hemos generado un entorno de desarrollo sencillo para que puedas experimentar con código de ejemplo y crear y ejecutar el agente que creaste en el entorno de desarrollo de Azure AI Foundry.

La extensión de Azure AI Foundry proporciona herramientas para ayudarte a crear, probar e implementar modelos y aplicaciones de IA directamente desde VS Code. Ofrece operaciones simplificadas para interactuar con tus modelos, agentes e hilos sin salir de tu entorno de desarrollo. Haz clic en el icono de Azure AI Foundry a la izquierda para ver más.

¡Sigue las instrucciones a continuación para empezar!

## Abre la terminal

Presiona ``Ctrl-` `` para abrir una ventana de terminal.

## Ejecutar el agente localmente

Para ejecutar el agente creado en AI Foundry y ver el resultado en la terminal, ejecute el siguiente comando:

```bash
python run_agent.py
```

## Actualizar la configuración del agente

En la barra de actividades izquierda:

- Abra la pestaña Azure AI Foundry en la barra de navegación.
- En "Recursos", expanda la sección "Agentes" y haga clic en el nombre del agente correspondiente.
- Haga clic en "Abrir archivo YAML".
- Realice los cambios necesarios en la definición del agente.
- Actualice el agente en Azure AI Foundry.

## Agregar, aprovisionar e implementar la aplicación web que usa el agente.

Para agregar una aplicación web que usa el agente, ejecute el siguiente comando. Cuando se le pregunte qué desea hacer con los archivos, le sugerimos seleccionar "Sobrescribir con versiones de la plantilla".

```bash
azd init -t https://github.com/Azure-Samples/get-started-with-ai-agents
```

Puede aprovisionar e implementar esta aplicación web usando:

```bash
azd up
```

Para eliminar la aplicación web y evitar cargos, ejecute:

```bash
azd down
```

## Continuar en el escritorio local

Puede seguir trabajando localmente en VS Code Desktop haciendo clic en "Continuar en el escritorio..." en la parte inferior izquierda de esta pantalla. Asegúrate de llevar el archivo .env contigo siguiendo estos pasos:

- Haz clic derecho en el archivo .env
- Selecciona "Descargar"
- Mueve el archivo de la carpeta "Descargas" al directorio local del repositorio Git
- En Windows, deberás cambiar el nombre del archivo a .env haciendo clic derecho en "Cambiar nombre..."

## Más ejemplos

Consulta la [biblioteca cliente de Azure AI Projects para Python](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-projects/README.md) para obtener más información sobre el uso de este SDK.

Solución de problemas

- Si va a instanciar su cliente mediante un punto de conexión en un proyecto de Azure AI Foundry, asegúrese de que el punto de conexión esté configurado en el script `run_agent` como `https://{your-foundry-resource-name}.services.ai.azure.com/api/projects/{your-foundry-project-name}`