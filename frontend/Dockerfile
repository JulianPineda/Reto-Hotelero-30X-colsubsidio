FROM node:20-alpine AS build

WORKDIR /app

# Vite inlines VITE_* vars at build time — they must be real env vars
# during `npm run build`, not just present in a .env file inside the image.
ARG VITE_API_BASE_URL
ARG VITE_WS_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_WS_BASE_URL=${VITE_WS_BASE_URL}

COPY package.json ./
RUN npm install

COPY . .
RUN npm run build

FROM nginx:1.25-alpine

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
