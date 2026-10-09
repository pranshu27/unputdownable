FROM 409344278376.dkr.ecr.us-east-2.amazonaws.com/node_hardened_image:v1
 
WORKDIR /app
 
COPY package*.json ./
COPY scripts/verify-picomatch.mjs scripts/verify-picomatch.mjs
 
RUN npm ci
RUN npm run verify:picomatch
 
COPY . .
 
RUN npm run build
 
EXPOSE 3000
 
CMD ["npm", "start"]