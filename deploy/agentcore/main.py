"""AgentCore Runtime entrypoint for the CareerAgent deployment package.

This file sits at the root of the deployment zip and boots the AgentCore
adapter defined in app/agentcore_runtime.py. The FastAPI service and the
persistence layer are intentionally not part of this package.
"""

from app.agentcore_runtime import agentcore_app

if __name__ == "__main__":
    agentcore_app.run()
