FROM golang:1.24-alpine AS builder

RUN apk add --no-cache git

WORKDIR /app
COPY go.mod go.sum* ./
RUN go mod download
COPY . .
RUN go build -o datadog-demo .

FROM alpine:latest

WORKDIR /app
COPY --from=builder /app/datadog-demo .
EXPOSE 8080
CMD ["./datadog-demo"]
