plugins {
    java
    application
    id("com.github.johnrengelman.shadow") version "8.1.1"
}

group = "org.fhir4ds"
version = "1.0.0"

repositories {
    mavenCentral()
}

val cqlVersion = "3.20.1"
val hapiVersion = "7.4.0"

dependencies {
    // CQL Translator (CQL -> ELM)
    implementation("info.cqframework:cql-to-elm:$cqlVersion")
    implementation("info.cqframework:model:$cqlVersion")
    implementation("info.cqframework:elm:$cqlVersion")
    implementation("info.cqframework:cql:$cqlVersion")

    // CQL Engine (evaluation runtime)
    implementation("info.cqframework:engine:$cqlVersion")
    implementation("info.cqframework:engine-fhir:$cqlVersion")

    // Jackson-based ELM serialization (needed by engine)
    implementation("info.cqframework:elm-jackson:$cqlVersion")
    implementation("info.cqframework:model-jackson:$cqlVersion")

    // HAPI FHIR R4
    implementation("ca.uhn.hapi.fhir:hapi-fhir-structures-r4:$hapiVersion")
    implementation("ca.uhn.hapi.fhir:hapi-fhir-base:$hapiVersion")

    // JSON parsing
    implementation("com.google.code.gson:gson:2.10.1")

    // CLI
    implementation("info.picocli:picocli:4.7.5")

    // Logging
    implementation("org.slf4j:slf4j-api:2.0.9")
    implementation("org.slf4j:slf4j-simple:2.0.9")

    // Apache Commons (used by CqlEngine internals)
    implementation("org.apache.commons:commons-lang3:3.14.0")
}

application {
    mainClass.set("org.fhir4ds.benchmark.ClinicalReasoningBenchmark")
}

java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}

tasks.withType<com.github.jengelman.gradle.plugins.shadow.tasks.ShadowJar> {
    mergeServiceFiles()
    manifest {
        attributes("Main-Class" to "org.fhir4ds.benchmark.ClinicalReasoningBenchmark")
    }
}
