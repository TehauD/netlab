# LinkedIn Connection Graph

> Interactive visualization of your LinkedIn network using local-first analytics and relationship mapping.

![JavaScript](https://img.shields.io/badge6-yellow
![Privacy](https://img.shields.io/badge/Privacy--green
![License](https://img.shields.io/badge/License-MIT-blue)

view

LinkedIn Connection Graph transforms a LinkedIn `Connections.csv` export into an interactive network visualization that reveals patterns across your professional relationships.

The application runs entirely in the browser and allows you to:

- Explore professional connection clusters
- Identify high-density company networks
- Analyze growth of your network over time
- Discover relationship patterns
- Visualize organizational communities

No data leaves your machine.

---

## Features

### Interactive Network Visualization

- Force-directed graph rendering
- Smooth pan and zoom
- Interactive node selection
- Dynamic clustering
- Real-time filtering

### Network Analytics

- Search by name
- Search by company
- Largest employer identification
- Company cluster analysis
- Temporal connection analysis

### Privacy First

- No backend services
- No accounts required
- No API keys
- No telemetry
- No tracking
- Local browser processing only

### Clustering Modes

| Mode | Purpose |
|--------|------------|
| Company | Groups by employer |
| Recency | Groups by year connected |
| None | Raw relationship network |

---

## How It Works

```text
LinkedIn Connections.csv
            │
            ▼
       CSV Parser
            │
            ▼
     Connection Model
            │
            ▼
      Graph Generator
            │
            ▼
 Interactive Visualization
```

---

## Getting Your Data

Export your LinkedIn connections:

```text
LinkedIn
 └── Settings & Privacy
      └── Data Privacy
           └── Get a Copy of Your Data
                └── Connections
```

LinkedIn will generate:

```text
Connections.csv
```

Load the file into the application and begin exploring your network.

---

## Running Locally

Clone the repository:

```bash
git clone https://github.com/TehauD/linkedin-connection-graph.git
```

Navigate to the project:

```bash
cd linkedin-connection-graph
```

Serve locally:

```bash
python -m http.server 8000
```

Open:

```text
http://localhost:8000
```

---

## Project Structure

```text
linkedin-connection-graph/
│
├── index.html
├── linkedin-graph.js
├── README.md
│
└── assets/
    ├── screenshot.png
    └── logo.png
```

---

## Why This Project Exists

Professional networks contain valuable signals that are difficult to identify through traditional list views.

This project explores:

- Network density
- Career communities
- Organizational influence
- Relationship growth
- Connection clustering

while maintaining complete ownership of personal data.

---

## Future Roadmap

### Planned Enhancements

- Community detection algorithms
- Network centrality scoring
- Timeline playback mode
- Geographic clustering
- Knowledge graph integration
- Relationship recommendations
- TensorFlow.js analytics

### Enterprise Concepts

- Azure deployment
- Entra authentication
- Semantic relationship search
- Organizational network analysis
- AI-powered networking insights

---

## Portfolio Context

This project is part of my broader work exploring:

- Machine Learning
- Graph Analytics
- Enterprise AI
- Human-centered data visualization
- Relationship intelligence systems

---

## Author

**Tehau Debarthe**

Machine Learning Engineer | Enterprise AI Architect | Builder

GitHub: https://github.com/TehauD

---

## License

MIT
