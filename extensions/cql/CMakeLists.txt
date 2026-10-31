cmake_minimum_required(VERSION 3.5)

set(TARGET_NAME cql)
set(EXTENSION_NAME ${TARGET_NAME}_extension)
set(LOADABLE_EXTENSION_NAME ${TARGET_NAME}_loadable_extension)

project(${TARGET_NAME})

include_directories(src/include src)

set(EXTENSION_SOURCES
    src/cql_extension.cpp
    src/cql/datetime.cpp
    src/cql/interval.cpp
    src/cql/age.cpp
    src/cql/clinical.cpp
    src/cql/valueset.cpp
    src/cql/aggregate.cpp
    src/cql/ratio.cpp
    src/cql/quantity.cpp
    src/cql/boundary.cpp
    src/cql/math.cpp
src/cql/logical.cpp
)

build_static_extension(${TARGET_NAME} ${EXTENSION_SOURCES})
build_loadable_extension(${TARGET_NAME} "" ${EXTENSION_SOURCES})

# PERF phase2: the valueset cache uses std::shared_mutex (C++17) for
# chunk-level shared reads. duckdb's re2 third_party dir adds a
# directory-scoped -std=c++11 that bleeds into these targets; re-assert
# C++17 AFTER target creation so it wins the command line ordering.
target_compile_options(${EXTENSION_NAME} PRIVATE -std=c++17)
target_compile_options(${LOADABLE_EXTENSION_NAME} PRIVATE -std=c++17)

install(
    TARGETS ${EXTENSION_NAME}
    EXPORT "${DUCKDB_EXPORT_SET}"
    LIBRARY DESTINATION "${INSTALL_LIB_DIR}"
    ARCHIVE DESTINATION "${INSTALL_LIB_DIR}"
)
