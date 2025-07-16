# News Chatbot Application

## Demo

🎥 **[Voir la démonstration du chatbot en action](https://youtu.be/TeCmgvcuW0E)**



## Partie 2 : Questions théoriques sur le chatbot

Cette section détaille l'approche que je propose pour le déploiement en production du chatbot, en particulier sur l'écosystème Azure. Je tiens à préciser que mon expérience pratique avec Azure est en cours de développement. Ma réflexion se base donc sur mes connaissances en développement, en conteneurisation avec Docker, et sur mes recherches concernant les bonnes pratiques de déploiement cloud.

### 3.1 Architecture et Déploiement en Production

Pour déployer la solution sur Azure, je propose une approche progressive en utilisant des services managés qui simplifient la gestion de l'infrastructure, ce qui est idéal quand on n'est pas encore un expert de la plateforme.

Le plan se déroulerait en trois axes principaux :

*   **Hébergement du Backend (Python/FastAPI)** : Le backend, que j'ai développé avec `FastAPI`, est déjà conçu pour être conteneurisé. La première étape serait de créer une image Docker de l'application. Ensuite, pour héberger ce conteneur, le service **Azure Container Apps (ACA)** me semble le plus pertinent. Il est conçu pour exécuter des conteneurs sans avoir à gérer la complexité d'un orchestrateur comme Kubernetes (AKS). L'avantage majeur est qu'il gère nativement la mise à l'échelle (scalability) et les requêtes HTTP, ce qui correspond parfaitement à notre besoin.

*   **Hébergement du Frontend (React)** : Pour l'interface en React, je pense que le service **Azure Static Web Apps (SWA)** serait la solution de choix. Il est spécifiquement optimisé pour héberger des applications web statiques et s'intègre parfaitement avec GitHub pour automatiser le déploiement à chaque mise à jour du code.
  
*   **Gestion des Secrets et de la Configuration** : Un point crucial est la gestion de notre `OPENROUTER_API_KEY`. J'utiliserais **Azure Key Vault**, un service qui permet de stocker les variables secretes du .env . Notre application sur Azure Container Apps pourrait alors s'authentifier de manière sécurisée auprès du Key Vault  pour récupérer la clé au démarrage, sans qu'elle ne soit jamais exposée.

Pour centraliser la gestion, tous ces services seraient créés au sein d'un seul **Groupe de Ressources Azure**, ce qui facilite le suivi des coûts et des permissions.

**Services Azure et Justification :**

*   **Azure Container Apps (ACA)** : Pour le backend, car il est basé sur les conteneurs (une technologie que je maîtrise) et gère l'autoscaling.
*   **Azure Static Web Apps (SWA)** : Pour le frontend, car il est présenté comme  simple, peu coûteux et automatisé pour les projets React.
*   **Azure Key Vault** : Pour la sécurité des secrets, c'est la pratique standard et la plus robuste.
*   **Azure Container Registry (ACR)** : Pour stocker nos images Docker privées avant de les déployer.
*   **Application Insights** : Pour le monitoring, afin de surveiller la performance et les erreurs.

**Estimation des Coûts Mensuels :**

Estimer les coûts précisément sans trafic réel est difficile. Cependant, l'avantage des services choisis est leur modèle de paiement à l'usage avec des quotas gratuits généreux. Pour un trafic modéré, on peut s'attendre à une facture très raisonnable. Azure Container Apps et Static Web Apps ont des niveaux gratuits ou très peu coûteux pour démarrer. Je pense qu'on pourrait viser un coût initial **inférieur à 30-40 € par mois**, qui n'augmenterait qu'en cas de succès et de trafic important. C'est un point à valider avec un suivi attentif lors des premières semaines.

**Considérations de Sécurité et Permissions :**

La sécurité est primordiale. L'accès au backend depuis Internet serait géré par Azure Container Apps, qui expose une URL HTTPS. Les permissions seraient granulaires : l'identité de l'application n'aurait que le droit de lire les secrets, pas de les modifier. Pour le déploiement, il faudrait un principal de service (`service principal`) avec les droits nécessaires pour pousser une image sur ACR et mettre à jour l'application ACA, mais ces droits ne seraient utilisés que par le système de CI/CD.

### 3.2 Stratégie de Mise en Production

Je m'appuierais sur **GitHub Actions** pour l'intégration et le déploiement continus (CI/CD). Le workflow serait configuré pour se déclencher à chaque `push` sur la branche `main` :

1.  **Build & Test** : Lancement des tests automatisés pour le backend.
2.  **Dockerize** : Si les tests passent, construction de l'image Docker du backend.
3.  **Push to Registry** : Envoi de l'image vers notre **Azure Container Registry (ACR)**.
4.  **Deploy** : Déclenchement d'une mise à jour sur **Azure Container Apps** pour utiliser la nouvelle image. En parallèle, le pipeline de **Azure Static Web Apps** se déclencherait automatiquement pour déployer le frontend.

**Monitoring et Logs :**

Azure propose **Application Insights**. Il faudrait que je me forme sur son utilisation pour créer des tableaux de bord et des alertes pertinentes (par exemple, si le taux d'erreur dépasse 5%).

En complément, pour le suivi spécifique des interactions avec le LLM, on pourrait tout à fait intégrer un outil comme **LangSmith**, que je connais mieux. Il offrirait une visibilité très fine sur les étapes du LangGraph (recherche web, appel au LLM), ce qui serait précieux pour le débogage et l'amélioration de la qualité des réponses. Les deux outils seraient complémentaires : Application Insights pour l'infrastructure, LangSmith pour l'intelligence applicative.

**Gestion des Erreurs :**

Dans le code que j'ai fourni (`backend/app.py`), une première gestion des erreurs est en place avec la librairie `Tenacity`, qui assure des re-tentatives avec un temps d'attente exponentiel en cas d'échec des appels à l'API d'OpenRouter. En production, il faudrait renforcer cela avec :

*   Un **global exception handler** dans FastAPI pour s'assurer que même les erreurs inattendues retournent une réponse JSON propre et non une stack trace.
*   Des **alertes dans Application Insights** si le nombre d'erreurs `HTTP 500` ou `429` (rate limit) dépasse un certain seuil.

**Backup et Récupération (Approche *Stateless*) :**

Notre application est conçue pour être **stateless** (sans état). Elle ne stocke aucune donnée utilisateur persistante dans une base de données. Cela simplifie énormément la stratégie de backup :

*   Le **code source** est sauvegardé par `Git` sur GitHub.
*   Les **images Docker** sont versionnées et stockées sur `Azure Container Registry.
*   Les **secrets** sont en sécurité dans `Azure Key Vault`, qui a ses propres mécanismes de sauvegarde et de récupération.

La principale "donnée" à protéger est donc le code et la configuration de l'infrastructure.
