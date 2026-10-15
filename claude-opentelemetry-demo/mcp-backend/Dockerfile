FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build
COPY pom.xml .
RUN mvn -B -q dependency:go-offline
COPY src ./src
RUN mvn -B -q package -DskipTests

# The Java agent extension that reads a traceparent from the MCP URL.
FROM maven:3.9-eclipse-temurin-21 AS propagator
WORKDIR /build
COPY propagator/pom.xml .
RUN mvn -B -q dependency:go-offline
COPY propagator/src ./src
RUN mvn -B -q package -DskipTests

FROM eclipse-temurin:21-jre
WORKDIR /app
# The same OpenTelemetry Java agent release the reference backend runs.
# Compose turns it on for the two servers through JAVA_TOOL_OPTIONS; the
# one-shot roles run without it.
ADD https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v2.32.0/opentelemetry-javaagent.jar /otel/opentelemetry-javaagent.jar
COPY --from=propagator /build/target/mcp-url-propagator.jar /otel/mcp-url-propagator.jar
COPY --from=build /build/target/app.jar ./app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
