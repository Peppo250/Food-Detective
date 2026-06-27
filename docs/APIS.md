# 🌐 Free Public APIs Reference

Food Detective operates entirely on free, open, and public APIs. It requires **no API keys** or premium subscriptions. All API fetches are executed asynchronously in parallel to minimize latency.

---

## 1. OpenFoodFacts API

* **Endpoint**: `https://world.openfoodfacts.org/cgi/search.pl`
* **Purpose**: Retrieves additive tags, E-numbers, and ingredient analysis parameters (such as palm oil and vegan status).
* **Usage**:
  ```http
  GET /cgi/search.pl?search_terms={ingredient_name}&search_simple=1&action=process&json=1&page_size=3
  ```
* **Properties Extracted**:
  * `ingredients_analysis_tags`: Checks for `"en:vegan"` and `"en:palm-oil"`.
  * `additives_original_tags`: Resolves the specific additive taxonomy slug to confirm if the parsed token represents a known food additive.

---

## 2. OpenFDA API

* **Endpoint**: `https://api.fda.gov/food/event.json`
* **Purpose**: Fetches aggregate adverse event reports reported to the US Food and Drug Administration (FDA).
* **Usage**:
  ```http
  GET /food/event.json?search=reactions:"{ingredient_name}"&limit=1
  ```
* **Properties Extracted**:
  * `meta.results.total`: Used as a metric for adverse events. If the count exceeds **500**, the Scorer automatically flags the ingredient under the `avoid` category.

---

## 3. Wikipedia API

* **Endpoint**: `https://en.wikipedia.org/api/rest_v1/page/summary/{Title}`
* **Purpose**: Retrieves plain English summaries of complex chemical terms, which are then simplified for children.
* **Usage**:
  ```http
  GET /api/rest_v1/page/summary/{Title}
  ```
* **Fallback Strategy**:
  If the direct lookup fails, the query is retried with alt suffixes:
  1. `{Ingredient_Name} (food additive)`
  2. `{Ingredient_Name} (additive)`
* **Properties Extracted**:
  * `extract`: The first two sentences of the page extract are parsed, sent to the Explainer module, and simplified (e.g. replacing words like "synthetic" with "man-made").

---

## 4. Wikidata SPARQL Query API

* **Endpoint**: `https://query.wikidata.org/sparql`
* **Purpose**: Queries structured semantic data to map chemical terms back to European E-numbers (P628).
* **Usage**:
  ```http
  GET /sparql?query={SPARQL_Query}&format=json
  ```
* **Query Format**:
  ```sparql
  SELECT ?item ?e_number WHERE {
    ?item rdfs:label "{clean_name}"@en.
    OPTIONAL { ?item wdt:P628 ?e_number. }
  } LIMIT 1
  ```
* **Properties Extracted**:
  * `e_number`: Used to match E-number databases and append E-numbers to safety warnings (e.g. mapping "tartrazine" to "E102").
