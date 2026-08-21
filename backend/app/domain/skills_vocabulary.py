"""The skill vocabulary: canonical names mapped to the surface forms that mean them.

Data, not logic. Adding a skill is editing this dictionary, and nothing else in the codebase
needs to know. The extractor compiles whatever is here.

This is the floor beneath skill scoring, not the whole of it. ADR 0011: a model reads each
posting once at refresh time and its findings are unioned on top, because a list can only ever
find terms someone thought to write down, and real descriptions say things like "comfortable
owning a service end to end" that no vocabulary anticipates.

The floor still matters. It is free, it is identical on every run, and it is what the interface
can show a student term by term. When inference is unavailable this is the answer, and the score
says so rather than presenting a thinner reading as the same thing.

Canonical names are written the way a person writes them — `PostgreSQL`, `Node.js`, `C++` — so
they can be printed in the interface without a lookup table for display.
"""

# Canonical name -> aliases. The canonical name is always matched too; it does not need to be
# repeated in its own alias list.
VOCABULARY: dict[str, list[str]] = {
    # --- Languages -------------------------------------------------------------------
    "Python": ["py"],
    "JavaScript": ["js", "ecmascript"],
    "TypeScript": ["ts"],
    "Java": [],
    "C": [],
    "C++": ["cpp", "c plus plus"],
    "C#": ["csharp", "c sharp"],
    "Go": ["golang"],
    "Rust": [],
    "Ruby": [],
    "PHP": [],
    "Swift": [],
    "Kotlin": [],
    "Objective-C": ["objective c", "objc"],
    "Scala": [],
    "R": [],
    "MATLAB": [],
    "Perl": [],
    "Haskell": [],
    "Elixir": [],
    "Dart": [],
    "Lua": [],
    "Assembly": ["assembler"],
    "VHDL": [],
    "Verilog": [],
    "SQL": [],
    "Bash": ["shell scripting", "shell script"],
    "PowerShell": [],
    "HTML": ["html5"],
    "CSS": ["css3"],
    "Sass": ["scss"],
    "XML": [],
    "JSON": [],
    "YAML": [],
    # --- Frontend --------------------------------------------------------------------
    "React": ["react.js", "reactjs"],
    "React Native": ["react-native"],
    "Vue": ["vue.js", "vuejs"],
    "Angular": ["angular.js", "angularjs"],
    "Svelte": ["sveltekit"],
    "Next.js": ["nextjs"],
    "Redux": [],
    "jQuery": [],
    "Tailwind CSS": ["tailwind", "tailwindcss"],
    "Bootstrap": [],
    "Webpack": [],
    "Vite": [],
    "GraphQL": [],
    "REST": ["rest api", "restful", "rest apis"],
    "gRPC": [],
    "WebSockets": ["websocket"],
    "Accessibility": ["a11y", "wcag", "screen reader"],
    "Responsive design": ["responsive web design"],
    # --- Backend and frameworks ------------------------------------------------------
    "Node.js": ["nodejs", "node"],
    "Express": ["express.js", "expressjs"],
    "Django": [],
    "Flask": [],
    "FastAPI": [],
    "Spring": ["spring boot", "springboot"],
    "Rails": ["ruby on rails", "ruby-on-rails"],
    "Laravel": [],
    ".NET": ["dotnet", ".net core", "asp.net"],
    "Microservices": ["microservice", "micro-services"],
    "API design": ["api development"],
    "Celery": [],
    "RabbitMQ": [],
    "Kafka": ["apache kafka"],
    # --- Data ------------------------------------------------------------------------
    "PostgreSQL": ["postgres", "psql"],
    "MySQL": [],
    "SQLite": [],
    "MongoDB": ["mongo"],
    "Redis": [],
    "Elasticsearch": ["elastic search", "opensearch"],
    "Cassandra": [],
    "DynamoDB": [],
    "Snowflake": [],
    "BigQuery": ["big query"],
    "Redshift": [],
    "Databricks": [],
    "Spark": ["apache spark", "pyspark"],
    "Hadoop": [],
    "Airflow": ["apache airflow"],
    "dbt": [],
    "ETL": ["etl pipelines", "elt"],
    "Data modelling": ["data modeling", "dimensional modeling"],
    "Data warehousing": ["data warehouse"],
    "Data pipelines": ["data pipeline"],
    "Pandas": [],
    "NumPy": [],
    "Tableau": [],
    "Power BI": ["powerbi"],
    "Looker": [],
    "Excel": ["microsoft excel", "spreadsheets"],
    "Statistics": ["statistical analysis", "statistical modeling"],
    "A/B testing": ["ab testing", "split testing", "experimentation"],
    # --- ML --------------------------------------------------------------------------
    "Machine learning": ["ml", "machine-learning"],
    "Deep learning": [],
    "TensorFlow": [],
    "PyTorch": ["torch"],
    "scikit-learn": ["sklearn", "scikit learn"],
    "NLP": ["natural language processing"],
    # `cv` is deliberately not an alias here. In a job posting CV means curriculum vitae far
    # more
    # often than computer vision, and reading a request for a resume as a machine-learning
    # requirement would lower a graduate's score against a demand nobody made.
    "Computer vision": ["image recognition", "object detection"],
    "LLMs": ["large language models", "large language model", "generative ai", "genai"],
    "Recommender systems": ["recommendation systems", "recommendation engine"],
    "Feature engineering": [],
    "Model deployment": ["mlops", "model serving"],
    # --- Infrastructure --------------------------------------------------------------
    "AWS": ["amazon web services"],
    "Azure": ["microsoft azure"],
    "GCP": ["google cloud", "google cloud platform"],
    "Docker": ["containers", "containerisation", "containerization"],
    "Kubernetes": ["k8s", "eks", "gke"],
    "Terraform": [],
    "Infrastructure as code": ["iac"],
    "CI/CD": [
        "ci cd",
        "continuous integration",
        "continuous delivery",
        "continuous deployment",
    ],
    "Jenkins": [],
    "GitHub Actions": ["github action"],
    "Linux": ["unix"],
    "Nginx": [],
    "Serverless": ["lambda", "aws lambda", "cloud functions"],
    # Bare `monitoring` matched "actively monitoring the premises" and "monitoring product
    # levels". The tools and the qualified phrase are unambiguous; the bare verb is not.
    "Observability": [
        "prometheus",
        "grafana",
        "datadog",
        "application monitoring",
        "system monitoring",
        "infrastructure monitoring",
    ],
    # `networking` alone is as often the careers-page benefit as the discipline.
    "Computer networking": ["tcp/ip", "dns", "load balancing", "network administration"],
    "Distributed systems": ["distributed system"],
    "Scalability": ["scaling", "high availability"],
    "Performance optimisation": ["performance optimization", "performance tuning"],
    "Caching": ["cache"],
    # --- Practice --------------------------------------------------------------------
    "Git": ["github", "gitlab", "version control"],
    "Agile": ["scrum", "kanban", "sprints"],
    "Code review": ["peer review", "code reviews"],
    "Unit testing": ["unit test", "unit tests"],
    "Integration testing": ["integration test", "integration tests"],
    "Test automation": ["automated testing", "test-driven development", "tdd"],
    "Debugging": ["troubleshooting"],
    "Selenium": [],
    "Cypress": [],
    "Playwright": [],
    "Jest": [],
    "pytest": [],
    "JUnit": [],
    "Documentation": ["technical writing", "technical documentation"],
    "Data structures": ["data structure"],
    "Algorithms": ["algorithm design"],
    "Object-oriented programming": ["oop", "object oriented programming"],
    "Functional programming": [],
    "System design": ["software architecture", "architectural design"],
    # Bare `security` is deliberately absent. In 400 real postings it matched
    # `Security Officer` guard roles, "safety, security, quality guidelines"
    # and "financial security" - a domain word, not a skill. Only the
    # qualified forms name the discipline.
    # word, not a skill. Only the qualified forms name the discipline.
    "Cybersecurity": [
        "application security",
        "appsec",
        "secure coding",
        "information security",
        "infosec",
        "security engineering",
    ],
    "Authentication": ["oauth", "sso", "jwt"],
    "Cryptography": ["encryption"],
    "Penetration testing": ["pen testing", "ethical hacking"],
    # Bare `compliance` appeared in the wage-and-benefits boilerplate of nearly
    # every posting sampled - "in compliance with the local wage requirements".
    # The named frameworks are the skill; the word alone is legal text.
    # sampled - "in compliance with the local wage requirements". The frameworks are the skill.
    "Regulatory compliance": ["soc 2", "gdpr", "hipaa", "pci dss", "compliance program"],
    # --- Platform and tools ----------------------------------------------------------
    "iOS": [],
    "Android": [],
    "Flutter": [],
    "Unity": [],
    "Embedded systems": ["embedded software", "firmware"],
    "Figma": [],
    "Jira": [],
    "Confluence": [],
    "Salesforce": [],
    "SAP": [],
    "Blockchain": ["smart contracts", "solidity", "web3"],
    "Robotics": ["ros"],
    "Simulation": ["modeling and simulation"],
    "CAD": ["solidworks", "autocad"],
    # --- Transferable ----------------------------------------------------------------
    "Communication": ["written communication", "verbal communication"],
    "Teamwork": ["collaboration", "cross-functional", "cross functional"],
    "Problem solving": ["problem-solving", "analytical thinking"],
    "Leadership": ["mentoring", "mentorship"],
    "Project management": ["project planning"],
    "Stakeholder management": ["stakeholder engagement"],
    "Customer service": ["client service", "customer facing"],
    "Presentation": ["public speaking", "presenting"],
    "Time management": ["prioritisation", "prioritization"],
    "Research": ["user research", "market research"],
    # \	raining\ is removed deliberately: it made Teaching the most common "skill" in the index,
    # entirely from "paid training" and "we will provide you with the training" - a benefit the
    # employer offers, which is the opposite of a requirement.
    "Teaching": ["tutoring", "instructing", "curriculum development"],
    "Bilingual": ["fluent in french", "fluent in spanish", "multilingual"],
    "IT": ["information technology", "it support", "helpdesk", "help desk"],
    "Technical support": ["tech support"],
    "Quality assurance": ["qa"],
    "Business analysis": ["requirements gathering", "business requirements"],
    "Product management": ["product roadmap", "roadmapping"],
    "UX design": ["user experience design", "ux/ui", "ui/ux"],
    "Wireframing": ["prototyping", "mockups"],
    "SEO": ["search engine optimisation", "search engine optimization"],
    "Content creation": ["copywriting", "content writing"],
    "Social media": ["social media marketing"],
    "Google Analytics": ["ga4"],
    "CRM": ["hubspot"],
    "Accounting": ["bookkeeping", "financial reporting"],
    "Financial modelling": ["financial modeling", "forecasting"],
    "Budgeting": ["budget management"],
    "Supply chain": ["logistics", "inventory management"],
    "Data entry": [],
    "Scheduling": ["calendar management"],
}
