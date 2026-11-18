# TNT v2 frontend

See ../README.md. Run npm ci, then npm run dev. The same-origin /api proxy targets localhost:5000 in development and the backend service in Compose. npm test, npm run lint and npm run build verify the app. The sky atlas lives in a disposable iframe so removing the viewer tears down the third-party SDK's document, WebGL resources and listeners.
