FROM golang:1.25-alpine AS builder

WORKDIR /app
COPY go.mod ./
RUN go mod download
COPY main.go ./
RUN go build -o demo-app main.go

FROM alpine:latest
WORKDIR /app
COPY --from=builder /app/demo-app .
CMD ["./demo-app"]
