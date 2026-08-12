FROM golang:1.24-alpine AS builder

WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /jaeger-demo-app .

FROM alpine:3.20
RUN apk --no-cache add ca-certificates
COPY --from=builder /jaeger-demo-app /jaeger-demo-app
EXPOSE 8080
ENTRYPOINT ["/jaeger-demo-app"]
