Design Patterns Found in PricePoa Codebase
==========================================

## **Creational Patterns**

### **Singleton Pattern**
- **File**: `database\connection.py`
- **Class**: `DatabaseConnection`
- **Implementation**: Uses `_instance` class variable and overridden `__new__` method to ensure only one database connection instance exists throughout the application.
- **Purpose**: Provides a single point of access to the MongoDB connection, ensuring resource efficiency and consistent configuration.

### **Factory Pattern**
- **Files**: Multiple pipeline and intelligence modules
- **Examples**:
  - `scraper\pipelines\text_normalizer.py` - `TextNormalizer` creates normalization rules with default values
  - `scraper\pipelines\canonical_product_builder.py` - `CanonicalProductBuilder` constructs canonical products from extracted attributes
  - `scraper\pipelines\embedding_text_builder.py` - Builds embedding text for products
  - `intelligence\nlp\search_pipeline\ranker.py` - Implements different ranking strategies
  - `database\models.py` - Factory-style creation of database model instances
- **Purpose**: Encapsulates object creation logic, allowing the system to create objects without specifying their exact classes.

## **Structural Patterns**

### **Decorator Pattern**
- **Files**:
  - `intelligence\outbox\outbox.py` - Uses `@property` decorator for database access
  - `intelligence\nlp\search_pipeline\vector_search.py` - Property decorators for vector search configuration
- **Purpose**: Dynamically adds behavior to objects without modifying their structure, enhancing functionality through wrappers.

### **Pipeline Pattern** (Structural/Behavioural hybrid)
- **Files**: Scraper pipelines (`scraper\pipelines\*`)
- **Examples**: ValidationPipeline, NormalizationPipeline, MongoDBPipeline, etc.
- **Implementation**: Chain of responsibility where each pipeline component processes data and passes it to the next.
- **Purpose**: Decouples data processing steps, allowing flexible composition and reuse of processing logic.

## **Behavioural Patterns**

### **Observer Pattern**
- **Files**: Event-driven components throughout the codebase
- **Examples**:
  - `scraper\worker.py` & `scraper\scheduler.py` - Worker processes and scheduled tasks
  - `scraper\middleware\*` - Playwright and deduplication middlewares that observe scraping events
  - `intelligence\outbox\worker.py` - Watches MongoDB change streams for product updates
  - `intelligence\scheduler.py` - APScheduler for periodic intelligence tasks
  - `api\main.py` & `api\query_engine.py` - FastAPI application observing HTTP requests
- **Purpose**: Defines a one-to-many dependency between objects so that when one object changes state, all its dependents are notified and updated automatically.

### **Strategy Pattern**
- **Files**: Algorithm selection modules
- **Examples**:
  - Text normalization strategies in scraper pipelines
  - Ranking strategies in `intelligence\nlp\search_pipeline\ranker.py`
  - Query parsing strategies in NLP modules
- **Purpose**: Defines a family of algorithms, encapsulates each one, and makes them interchangeable, allowing the algorithm to vary independently from clients that use it.

### **Builder Pattern**
- **File**: `scraper\pipelines\canonical_product_builder.py`
- **Class**: `CanonicalProductBuilder`
- **Purpose**: Separates the construction of a complex object from its representation, allowing the same construction process to create different representations.

### **Transactional Outbox Pattern**
- **File**: `intelligence\outbox\outbox.py`
- **Purpose**: Ensures reliable message delivery between MongoDB and Qdrant by storing events in an "outbox" collection before publishing, providing eventual consistency.

## **Summary**

The codebase demonstrates strong adherence to architectural patterns, particularly around:
- **Resource management** (Singleton for database connections)
- **Flexible object creation** (Factory for pipelines and builders)
- **Event-driven architecture** (Observer for workers and schedulers)
- **Data processing pipelines** (Pipeline/Chain of Responsibility for data transformation)
- **Algorithm flexibility** (Strategy for normalization, ranking, and parsing)

These patterns contribute to a maintainable, scalable, and loosely coupled system where concerns are well-separated and components can be evolved independently.