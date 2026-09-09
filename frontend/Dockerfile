# Dev-mode image. No production build / nginx stage — a class demo runs the Vite
# dev server directly.
FROM node:20-slim

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
