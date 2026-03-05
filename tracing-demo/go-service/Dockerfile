FROM golang:1.24-alpine AS builder

# Install git for go mod download
RUN apk add --no-cache git

WORKDIR /app
COPY go.mod go.sum* ./
RUN go mod download
COPY main.go ./
RUN go build -o go-service main.go

FROM alpine:latest
WORKDIR /app
COPY --from=builder /app/go-service .
CMD ["./go-service"]
