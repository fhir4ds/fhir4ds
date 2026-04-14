cmake_minimum_required(VERSION 3.5)

set(TARGET_NAME fhirpath)
set(EXTENSION_NAME ${TARGET_NAME}_extension)
set(LOADABLE_EXTENSION_NAME ${TARGET_NAME}_loadable_extension)

project(${TARGET_NAME})

include_directories(src/include src)

set(EXTENSION_SOURCES
    src/fhirpath_extension.cpp
    src/fhirpath/lexer.cpp
    src/fhirpath/parser.cpp
    src/fhirpath/evaluator.cpp
)

build_static_extension(${TARGET_NAME} ${EXTENSION_SOURCES})
build_loadable_extension(${TARGET_NAME} "" ${EXTENSION_SOURCES})

install(
    TARGETS ${EXTENSION_NAME}
    EXPORT "${DUCKDB_EXPORT_SET}"
    LIBRARY DESTINATION "${INSTALL_LIB_DIR}"
    ARCHIVE DESTINATION "${INSTALL_LIB_DIR}"
)
