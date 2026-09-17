# Stage 1: Build the Go binary
FROM golang:1.22-alpine AS builder

WORKDIR /app

# Copy go.mod and go.sum
COPY go.mod ./
# Download dependencies
RUN go mod download

# Copy the source code
COPY . .

# Build the binary
RUN go build -o /scraper-go .

# Stage 2: Create a minimal runtime image
FROM alpine:latest

# Install ca-certificates for HTTPS calls
RUN apk --no-cache add ca-certificates

# Copy the binary from the builder
COPY --from=builder /scraper-go /scraper-go

# Set the entrypoint
ENTRYPOINT ["/scraper-go"]