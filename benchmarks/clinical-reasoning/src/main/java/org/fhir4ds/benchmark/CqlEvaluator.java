package org.fhir4ds.benchmark;

import org.cqframework.cql.cql2elm.CqlTranslator;
import org.cqframework.cql.cql2elm.DefaultModelInfoProvider;
import org.cqframework.cql.cql2elm.LibraryManager;
import org.cqframework.cql.cql2elm.LibrarySourceProvider;
import org.cqframework.cql.cql2elm.ModelManager;
import org.hl7.elm.r1.Library;
import org.hl7.elm.r1.VersionedIdentifier;
import org.hl7.elm_modelinfo.r1.ClassInfo;
import org.hl7.elm_modelinfo.r1.ModelInfo;
import org.hl7.elm_modelinfo.r1.TypeInfo;
import org.hl7.elm_modelinfo.r1.TypeSpecifier;
import org.hl7.elm_modelinfo.r1.serializing.jackson.XmlModelInfoReader;
import org.hl7.fhir.instance.model.api.IBaseResource;
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonSubTypes.Type;
import com.fasterxml.jackson.annotation.JsonTypeInfo;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.dataformat.xml.XmlMapper;
import org.opencds.cqf.cql.engine.data.CompositeDataProvider;
import org.opencds.cqf.cql.engine.data.DataProvider;
import org.opencds.cqf.cql.engine.execution.CqlEngine;
import org.opencds.cqf.cql.engine.execution.Environment;
import org.opencds.cqf.cql.engine.execution.ExpressionResult;
import org.opencds.cqf.cql.engine.fhir.model.R4FhirModelResolver;
import org.opencds.cqf.cql.engine.retrieve.RetrieveProvider;
import org.opencds.cqf.cql.engine.runtime.Code;
import org.opencds.cqf.cql.engine.runtime.DateTime;
import org.opencds.cqf.cql.engine.runtime.Interval;
import org.opencds.cqf.cql.engine.terminology.TerminologyProvider;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.regex.Pattern;

/**
 * CQL Evaluator - Wraps CQL-to-ELM translation and evaluation using the
 * cqframework engine.
 *
 * Translation phase: Uses CqlTranslator to convert CQL source to ELM.
 * Execution phase: Uses CqlEngine to evaluate CQL expressions per patient.
 */
public class CqlEvaluator {

    /**
     * Replacement MixIns for TypeInfo and TypeSpecifier that keep As.PROPERTY but rely on
     * qualifyModelInfoXml() having moved xsi:type to be the FIRST XML attribute.
     *
     * Root cause: AsPropertyTypeDeserializer.deserializeTypedFromObject() buffers all tokens
     * read BEFORE the type property into a TokenBuffer. In the bundled model info XMLs, xsi:type
     * is the LAST attribute (after baseType, namespace, name, …), so all preceding attributes
     * plus ALL child <element> nodes get buffered. ClassInfo is then deserialized via
     * TokenBuffer.Parser (not FromXmlParser), which lacks Jackson XML's unwrapped-list logic,
     * so ClassInfo.element stays empty and phantom entries from <elementTypeSpecifier> appear.
     *
     * Fix: qualifyModelInfoXml() reorders attributes to put xsi:type FIRST on every element
     * that has it. Then the very first FIELD_NAME token is "type", tb stays null, and Jackson
     * dispatches to the concrete type using the original FromXmlParser — preserving all
     * XML-specific behaviour including repeated-element list collection.
     */
    @JsonTypeInfo(use = JsonTypeInfo.Id.NAME, include = JsonTypeInfo.As.PROPERTY, property = "type")
    @JsonSubTypes({
        @Type(value = org.hl7.elm_modelinfo.r1.SimpleTypeInfo.class,   name = "ns4:SimpleTypeInfo"),
        @Type(value = org.hl7.elm_modelinfo.r1.ClassInfo.class,        name = "ns4:ClassInfo"),
        @Type(value = org.hl7.elm_modelinfo.r1.ChoiceTypeInfo.class,   name = "ns4:ChoiceTypeInfo"),
        @Type(value = org.hl7.elm_modelinfo.r1.IntervalTypeInfo.class, name = "ns4:IntervalTypeInfo"),
        @Type(value = org.hl7.elm_modelinfo.r1.ListTypeInfo.class,     name = "ns4:ListTypeInfo"),
        @Type(value = org.hl7.elm_modelinfo.r1.ProfileInfo.class,      name = "ns4:ProfileInfo"),
        @Type(value = org.hl7.elm_modelinfo.r1.TupleTypeInfo.class,    name = "ns4:TupleTypeInfo"),
    })
    private interface TypeInfoMixInAttribute {}

    @JsonTypeInfo(use = JsonTypeInfo.Id.NAME, include = JsonTypeInfo.As.PROPERTY, property = "type")
    @JsonSubTypes({
        @Type(value = org.hl7.elm_modelinfo.r1.NamedTypeSpecifier.class,          name = "ns4:NamedTypeSpecifier"),
        @Type(value = org.hl7.elm_modelinfo.r1.ListTypeSpecifier.class,           name = "ns4:ListTypeSpecifier"),
        @Type(value = org.hl7.elm_modelinfo.r1.IntervalTypeSpecifier.class,       name = "ns4:IntervalTypeSpecifier"),
        @Type(value = org.hl7.elm_modelinfo.r1.ChoiceTypeSpecifier.class,         name = "ns4:ChoiceTypeSpecifier"),
        @Type(value = org.hl7.elm_modelinfo.r1.ParameterTypeSpecifier.class,      name = "ns4:ParameterTypeSpecifier"),
        @Type(value = org.hl7.elm_modelinfo.r1.BoundParameterTypeSpecifier.class, name = "ns4:BoundParameterTypeSpecifier"),
        @Type(value = org.hl7.elm_modelinfo.r1.TupleTypeSpecifier.class,          name = "ns4:TupleTypeSpecifier"),
    })
    private interface TypeSpecifierMixInAttribute {}

    /**
     * Temp directory containing model info XML files extracted (and pre-processed) from the JAR.
     * DefaultModelInfoProvider reads from a filesystem path, so we extract once and reuse.
     *
     * Pre-processing fixes a namespace mismatch: the bundled FHIR/QICore/USCore model info XMLs
     * use the default namespace (xsi:type="ChoiceTypeSpecifier"), but XmlModelInfoReader's
     * TypeSpecifierMixIn only maps the ns4-prefixed form (xsi:type="ns4:ChoiceTypeSpecifier").
     * We rewrite the XML on extraction to add xmlns:ns4 and qualify all xsi:type values.
     *
     * We also disable FAIL_ON_UNKNOWN_PROPERTIES on the mapper to tolerate newer-schema model
     * info files that include elements not present in elm-modelinfo-3.20.1 POJOs.
     */
    private static final Path MODEL_INFO_DIR;
    /** Cached FHIR R4 model resolver — creating one initialises a full FHIR context (expensive). */
    private static final R4FhirModelResolver FHIR_MODEL_RESOLVER = new R4FhirModelResolver();

    static {
        try {
            // Rebuild XmlModelInfoReader's static mapper WITHOUT JakartaXmlBindAnnotationModule.
            //
            // Root cause: the JAXB module causes namespace-qualified element matching that
            // breaks list field deserialization in ClassInfo. Specifically:
            //   - <element> direct children of <typeInfo> are SKIPPED
            //   - <elementTypeSpecifier> grandchildren are added as phantom ClassInfo.element entries
            //
            // Without the JAXB module, Jackson uses pure field-name (local name) matching:
            //   - ClassInfo field "element" → <element> children ✓
            //   - ClassInfoElement field "elementTypeSpecifier" → nested <elementTypeSpecifier> ✓
            //   - TypeSpecifier dispatch via TypeSpecifierMixIn (xsi:type → ns4:XxxType) ✓
            java.lang.reflect.Field mapperField = XmlModelInfoReader.class.getDeclaredField("mapper");
            mapperField.setAccessible(true);
            XmlMapper existingMapper = (XmlMapper) mapperField.get(null);

            Class<?> typeInfoMixIn = existingMapper.findMixInClassFor(TypeInfo.class);
            Class<?> typeSpecMixIn = existingMapper.findMixInClassFor(TypeSpecifier.class);

            // Build a fresh mapper using the same Woodstox XmlFactory but without JAXB module.
            com.fasterxml.jackson.dataformat.xml.XmlFactory xmlFactory =
                (com.fasterxml.jackson.dataformat.xml.XmlFactory) existingMapper.getFactory();
            XmlMapper mapper = (XmlMapper)
                com.fasterxml.jackson.dataformat.xml.XmlMapper.builder(xmlFactory)
                    .defaultUseWrapper(false)
                    .defaultMergeable(Boolean.TRUE)
                    .enable(DeserializationFeature.ACCEPT_SINGLE_VALUE_AS_ARRAY)
                    .enable(com.fasterxml.jackson.databind.MapperFeature.USE_BASE_TYPE_AS_DEFAULT_IMPL)
                    .enable(com.fasterxml.jackson.databind.MapperFeature.ACCEPT_CASE_INSENSITIVE_ENUMS)
                    .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
                    .build();

            if (typeInfoMixIn != null)
                mapper.addMixIn(TypeInfo.class, TypeInfoMixInAttribute.class);
            if (typeSpecMixIn != null)
                mapper.addMixIn(TypeSpecifier.class, TypeSpecifierMixInAttribute.class);

            mapperField.set(null, mapper);

            // Extract model info XMLs from the JAR into a temp directory so
            // DefaultModelInfoProvider can read them via the filesystem.
            // During extraction, rewrite xsi:type values to use the ns4: prefix so they match
            // the existing TypeSpecifierMixIn / TypeInfoMixIn mappings in XmlModelInfoReader.
            MODEL_INFO_DIR = Files.createTempDirectory("cqframework-modelInfos");
            for (String xml : new String[]{
                    "fhir-modelinfo-4.0.1.xml",
                    "qicore-modelinfo-6.0.0.xml",
                    "uscore-modelinfo-6.1.0.xml"}) {
                try (InputStream is = CqlEvaluator.class.getResourceAsStream("/modelInfos/" + xml)) {
                    if (is != null) {
                        String content = new String(is.readAllBytes(), StandardCharsets.UTF_8);
                        content = qualifyModelInfoXml(content);
                        Files.write(MODEL_INFO_DIR.resolve(xml), content.getBytes(StandardCharsets.UTF_8));
                    }
                }
            }
        } catch (Exception e) {
            throw new RuntimeException("Failed to initialise CQL model info", e);
        }
    }

    /**
     * Rewrites a model info XML so that unqualified xsi:type values gain the ns4: prefix
     * expected by XmlModelInfoReader's TypeSpecifierMixIn / TypeInfoMixIn.
     *
     * Example: xsi:type="ChoiceTypeSpecifier" → xsi:type="ns4:ChoiceTypeSpecifier"
     *
     * The system-provided model info (system-modelinfo.xml) already uses ns4:-prefixed names,
     * but the FHIR/QICore/USCore model info files shipped with ecqm-content-qicore-2025 use
     * the default namespace (no prefix), which Jackson cannot match without this rewrite.
     */
    private static String qualifyModelInfoXml(String xml) {
        // Only process files that declare the default ELM model info namespace
        if (!xml.contains("xmlns=\"urn:hl7-org:elm-modelinfo:r1\"")) {
            return xml;
        }
        // Add an ns4 prefix declaration bound to the same namespace URI
        xml = xml.replace(
            "xmlns=\"urn:hl7-org:elm-modelinfo:r1\"",
            "xmlns=\"urn:hl7-org:elm-modelinfo:r1\" xmlns:ns4=\"urn:hl7-org:elm-modelinfo:r1\""
        );
        // Qualify all bare (no-colon) xsi:type attribute values with the ns4: prefix.
        // The regex matches only simple type names (letters/digits) with no namespace prefix.
        xml = xml.replaceAll("xsi:type=\"([A-Za-z][A-Za-z0-9]*)\"", "xsi:type=\"ns4:$1\"");

        // Move xsi:type to be the FIRST attribute on every element that has it.
        //
        // AsPropertyTypeDeserializer scans FIELD_NAME tokens until it finds the type
        // discriminator ("type" = xsi:type local name). Every token read BEFORE "type" is
        // buffered into a TokenBuffer. If xsi:type is last (as in the model info XMLs),
        // ALL preceding attributes AND all child <element> nodes are buffered, then replayed
        // through TokenBuffer.Parser. TokenBuffer.Parser is a plain JSON parser with no
        // Jackson-XML repeated-element-as-list logic, so ClassInfo.element stays empty.
        //
        // With xsi:type first, the very first FIELD_NAME token is "type" → tb == null →
        // Jackson dispatches to ClassInfo/ListTypeSpecifier/etc. using the original
        // FromXmlParser, which correctly collects repeated <element> children into a List.
        xml = xml.replaceAll(
            "(<[A-Za-z][A-Za-z0-9:]*)((?:\\s+(?!xsi:type)[A-Za-z][A-Za-z0-9:]*=\"[^\"]*\")+)(\\s+xsi:type=\"[^\"]*\")",
            "$1$3$2");
        return xml;
    }

    private final List<Path> includePaths;
    private LibraryManager libraryManager;
    private TerminologyProvider terminologyProvider;

    public CqlEvaluator(List<Path> includePaths) {
        this.includePaths = includePaths;
    }

    public void setTerminologyProvider(TerminologyProvider terminologyProvider) {
        this.terminologyProvider = terminologyProvider;
    }

    /**
     * Translate CQL text to ELM.
     */
    public TranslationResult translate(String cqlText) {
        long startTime = System.nanoTime();

        try {
            ModelManager modelManager = new ModelManager();
            // Use DefaultModelInfoProvider with the temp dir containing our model info XMLs.
            // The global XmlMapper is already patched (in static init) to ignore unknown
            // fields so the newer-schema XMLs load cleanly.
            modelManager.getModelInfoLoader().registerModelInfoProvider(
                new DefaultModelInfoProvider(MODEL_INFO_DIR), true);

            libraryManager = new LibraryManager(modelManager);

            // Register include paths so library includes resolve correctly.
            // Use VersionTolerantLibrarySourceProvider to handle minor version mismatches
            // (e.g. measure references Hospice '6.15.000' but only '6.18.000' is present).
            for (Path includePath : includePaths) {
                libraryManager.getLibrarySourceLoader().registerProvider(
                    new VersionTolerantLibrarySourceProvider(includePath)
                );
            }

            CqlTranslator translator = CqlTranslator.fromText(cqlText, libraryManager);

            // Check for errors
            List<?> errors = translator.getErrors();
            if (errors != null && !errors.isEmpty()) {
                StringBuilder sb = new StringBuilder("CQL translation errors: ");
                for (Object error : errors) {
                    sb.append(error.toString()).append("; ");
                }
                return new TranslationResult(sb.toString());
            }

            // Get the ELM library object
            Library elmLibrary = translator.toELM();

            long endTime = System.nanoTime();
            double translationTimeMs = (endTime - startTime) / 1_000_000.0;

            return new TranslationResult(elmLibrary, translationTimeMs);

        } catch (Exception e) {
            return new TranslationResult("Translation failed: " + e.getMessage());
        }
    }

    /**
     * Evaluate an ELM library for a specific patient using the CQL engine.
     */
    public EvaluationResult evaluate(Object elmLibrary, NdjsonDataProvider dataProvider,
                                      String patientId, Map<String, Object> parameters) {
        long startTime = System.nanoTime();

        try {
            if (!(elmLibrary instanceof Library)) {
                return new EvaluationResult(patientId, "No ELM library available");
            }

            Library lib = (Library) elmLibrary;
            VersionedIdentifier libraryId = lib.getIdentifier();

            // Wire up the FHIR R4 data provider (model resolver is a cached singleton)
            RetrieveProvider retrieveProvider = new FhirRetrieveProvider(dataProvider, patientId);
            CompositeDataProvider fhirDataProvider = new CompositeDataProvider(FHIR_MODEL_RESOLVER, retrieveProvider);

            Map<String, DataProvider> dataProviders = new HashMap<>();
            dataProviders.put("http://hl7.org/fhir", fhirDataProvider);
            // QICore and USCore profiles use the FHIR R4 model resolver
            dataProviders.put("http://hl7.org/fhir/us/qicore", fhirDataProvider);
            dataProviders.put("http://hl7.org/fhir/us/core", fhirDataProvider);

            // Create engine environment with the library manager from translate()
            Environment env = new Environment(libraryManager, dataProviders, terminologyProvider);
            CqlEngine engine = new CqlEngine(env);

            // Convert string parameters to CQL runtime types
            Map<String, Object> cqlParameters = convertParameters(parameters);

            // Evaluate all expressions in the library
            org.opencds.cqf.cql.engine.execution.EvaluationResult engineResult =
                engine.evaluate(libraryId, cqlParameters);

            // Extract expression results
            Map<String, Object> results = new LinkedHashMap<>();
            for (Map.Entry<String, ExpressionResult> entry : engineResult.expressionResults.entrySet()) {
                results.put(entry.getKey(), entry.getValue().value());
            }

            long endTime = System.nanoTime();
            double executionTimeMs = (endTime - startTime) / 1_000_000.0;

            return new EvaluationResult(patientId, executionTimeMs, results);

        } catch (Exception e) {
            return new EvaluationResult(patientId, "Evaluation failed: " + e.getMessage());
        }
    }

    /**
     * Convert string parameters to CQL runtime types (e.g., Measurement Period -> Interval<DateTime>).
     */
    private Map<String, Object> convertParameters(Map<String, Object> parameters) {
        Map<String, Object> converted = new HashMap<>();
        for (Map.Entry<String, Object> entry : parameters.entrySet()) {
            String key = entry.getKey();
            Object value = entry.getValue();

            if (value instanceof String) {
                String str = (String) value;
                // Parse "yyyy-MM-dd" date strings into DateTime
                if (str.matches("\\d{4}-\\d{2}-\\d{2}")) {
                    String[] parts = str.split("-");
                    DateTime dt = new DateTime(
                        BigDecimal.ZERO,
                        Integer.parseInt(parts[0]),
                        Integer.parseInt(parts[1]),
                        Integer.parseInt(parts[2])
                    );
                    converted.put(key, dt);
                    continue;
                }
            }
            converted.put(key, value);
        }

        // If we have separate start/end params, build the Measurement Period interval
        Object start = converted.remove("Measurement Period Start");
        Object end = converted.remove("Measurement Period End");
        if (start instanceof DateTime && end instanceof DateTime) {
            converted.put("Measurement Period", new Interval(start, true, end, true));
        }

        return converted;
    }

    /**
     * RetrieveProvider that serves FHIR resources from NdjsonDataProvider
     * for a specific patient.
     */
    private static class FhirRetrieveProvider implements RetrieveProvider {

        private final NdjsonDataProvider dataProvider;
        private final String patientId;

        FhirRetrieveProvider(NdjsonDataProvider dataProvider, String patientId) {
            this.dataProvider = dataProvider;
            this.patientId = patientId;
        }

        @Override
        public Iterable<Object> retrieve(String context, String contextPath, Object contextValue,
                                          String dataType, String templateId, String codePath,
                                          Iterable<Code> codes, String valueSet, String codeSystem,
                                          String codeComparator, String primaryKeyPath, Interval dateRange) {
            if (dataType == null) return Collections.emptyList();

            Map<String, List<IBaseResource>> patientResources =
                dataProvider.getResourcesForPatient(patientId);

            List<IBaseResource> resources = patientResources.getOrDefault(dataType, Collections.emptyList());
            return new ArrayList<>(resources);
        }
    }

    /**
     * Library source provider that resolves CQL includes from a directory.
     */
    /**
     * Library source provider that resolves CQL files from a directory and patches the
     * library version declaration to match the requested version.
     *
     * This handles minor version mismatches in ecqm-content-qicore-2025 where some measures
     * still reference older library versions (e.g. Hospice '6.15.000') while the repository
     * has been updated to a newer version (e.g. '6.18.000'). For benchmarking purposes,
     * we accept the newer library as a forward-compatible substitute.
     */
    private static class VersionTolerantLibrarySourceProvider implements LibrarySourceProvider {

        private static final Pattern LIBRARY_VERSION_PATTERN = Pattern.compile(
            "^(library\\s+\\S+\\s+version\\s+')[^']*(')", Pattern.MULTILINE);

        private final Path directory;

        VersionTolerantLibrarySourceProvider(Path directory) {
            this.directory = directory;
        }

        @Override
        public InputStream getLibrarySource(VersionedIdentifier libraryIdentifier) {
            String name = libraryIdentifier.getId();
            Path cqlFile = directory.resolve(name + ".cql");
            if (!Files.exists(cqlFile)) return null;
            try {
                String content = new String(Files.readAllBytes(cqlFile), StandardCharsets.UTF_8);
                String requestedVersion = libraryIdentifier.getVersion();
                if (requestedVersion != null) {
                    // Patch the library version declaration so the translator accepts it
                    content = LIBRARY_VERSION_PATTERN.matcher(content)
                        .replaceFirst("$1" + requestedVersion + "$2");
                }
                return new ByteArrayInputStream(content.getBytes(StandardCharsets.UTF_8));
            } catch (IOException e) {
                return null;
            }
        }
    }
}
