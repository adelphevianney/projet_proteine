FROM node:22-slim
WORKDIR /app
RUN chown node:node /app
# L'image node fournit l'utilisateur « node » sans privilèges : on installe et on lance tout avec lui.
USER node
COPY --chown=node:node package.json package-lock.json ./
RUN npm ci
COPY --chown=node:node . .
EXPOSE 5173
CMD ["npx", "vite", "--host", "0.0.0.0", "--port", "5173"]
