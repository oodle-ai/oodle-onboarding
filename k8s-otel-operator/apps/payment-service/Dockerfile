FROM eclipse-temurin:21-jdk-alpine AS build
WORKDIR /app
COPY App.java .
RUN javac App.java

FROM eclipse-temurin:21-jre-alpine
WORKDIR /app
COPY --from=build /app/*.class .
EXPOSE 8080
CMD ["java", "App"]
