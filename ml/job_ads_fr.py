"""Banque de phrases françaises des annonces synthétiques (toutes inventées, aucune donnée réelle).

Chaque réserve est partagée entre entraînement et évaluation par `ml.job_ads.split_pool` : les
annonces d'évaluation n'emploient aucune phrase vue à l'entraînement.
"""

from __future__ import annotations

from ml.job_ads_types import Sector

SECTORS: tuple[Sector, ...] = (
    Sector(
        "ia",
        (
            "Architecte en intelligence artificielle",
            "Ingénieur·e en apprentissage automatique",
            "Responsable technique IA générative",
            "Développeur·se d'agents conversationnels",
            "Spécialiste MLOps",
            "Scientifique de données principal·e",
        ),
        (
            "Concevoir des assistants basés sur de grands modèles de langage et leurs garde-fous.",
            "Mettre en place la recherche augmentée (RAG) sur les bases documentaires internes.",
            "Évaluer la qualité des réponses des modèles avec des jeux de tests versionnés.",
            "Industrialiser l'entraînement et le déploiement des modèles dans le nuage.",
            "Rédiger et maintenir les consignes système des assistants, revues par l'équipe "
            "conformité.",
            "Surveiller la dérive des modèles en production et proposer les réentraînements.",
            "Accompagner les équipes métier dans l'identification des cas d'usage de l'IA.",
            "Définir les règles de filtrage des contenus et les tester contre les attaques "
            "connues.",
            "Choisir entre modèles hébergés et modèles ouverts selon le coût et la "
            "confidentialité.",
            "Documenter les décisions d'architecture et les présenter au comité technique.",
            "Mesurer la latence et le coût par requête des agents déployés.",
            "Former les développeurs aux bonnes pratiques de l'ingénierie des invites.",
            "Mettre en place le filtrage des entrées contre l'injection d'invite et la validation "
            "des sorties.",
            "Organiser des exercices d'équipe rouge sur nos assistants avant chaque mise en "
            "production.",
            "Versionner les invites système et les jeux d'évaluation comme du code.",
            "Concevoir une plateforme d'agents qui permet aux équipes d'assembler outils, invites "
            "et flux de travail.",
            "Définir les garde-fous de chaque fonctionnalité d'IA : protection des données "
            "personnelles, limites d'usage, journalisation.",
            "Instrumenter les agents (traces, coûts, latence) et publier des tableaux de bord de "
            "qualité.",
            "Évaluer la résistance des modèles aux tentatives de contournement (jailbreak) et "
            "documenter les correctifs.",
            "Encadrer l'usage des outils appelés par les agents : permissions minimales et "
            "approbation humaine.",
            "Automatiser les suites de régression qui rejouent les conversations types à chaque "
            "changement.",
            "Rédiger la politique d'utilisation responsable de l'IA générative avec le service "
            "juridique.",
            "Comparer les réponses de plusieurs modèles de langage sur nos cas d'usage réels.",
            "Mettre en place la détection de dérive et les alertes sur la qualité des réponses.",
        ),
        (
            "Au moins cinq ans d'expérience en développement logiciel, dont deux en "
            "apprentissage automatique.",
            "Maîtrise de Python et des bibliothèques d'IA courantes.",
            "Expérience concrète de mise en production de modèles de langage.",
            "Bonne compréhension des risques propres à l'IA générative : hallucinations, "
            "injections d'invite, fuite de données.",
            "Capacité à vulgariser des sujets techniques auprès de gestionnaires.",
            "Diplôme en informatique, en génie ou dans un domaine connexe.",
            "Connaissance des cadres de gouvernance de l'IA, un atout.",
            "Aisance avec l'évaluation statistique des modèles.",
            "Expérience des architectures événementielles, un plus.",
        ),
        (
            "Python",
            "PyTorch",
            "AWS Bedrock",
            "Azure OpenAI",
            "LangChain",
            "PostgreSQL avec pgvector",
            "Docker",
            "GitHub Actions",
            "MLflow",
            "FastAPI",
            "Terraform",
            "OpenTelemetry",
        ),
    ),
    Sector(
        "logiciel",
        (
            "Développeur·se back-end",
            "Développeur·se full stack",
            "Architecte logiciel",
            "Ingénieur·e en fiabilité des sites (SRE)",
            "Chef·fe d'équipe développement",
            "Ingénieur·e DevOps",
        ),
        (
            "Développer de nouvelles fonctionnalités sur notre plateforme de réservation en ligne.",
            "Participer aux revues de code et au mentorat des développeurs juniors.",
            "Améliorer la couverture de tests automatisés et la qualité du code.",
            "Maintenir les chaînes d'intégration et de déploiement continus.",
            "Diagnostiquer les incidents de production et rédiger les analyses post-mortem.",
            "Concevoir des API REST robustes et bien documentées.",
            "Réduire la dette technique en collaboration avec le responsable produit.",
            "Optimiser les requêtes de base de données les plus coûteuses.",
            "Automatiser le provisionnement de l'infrastructure.",
            "Mettre en place l'observabilité : journaux, métriques et traces.",
            "Contribuer aux choix technologiques de l'équipe.",
            "Assurer une garde technique en rotation, une semaine sur six.",
        ),
        (
            "Trois ans d'expérience ou plus en développement professionnel.",
            "Bonne connaissance d'un langage typé comme Java, Kotlin, Go ou TypeScript.",
            "Habitude des méthodes agiles et du travail en petites itérations.",
            "Sens du détail et goût pour le code lisible.",
            "Expérience des conteneurs et de leur orchestration.",
            "Bilinguisme français-anglais, à l'oral comme à l'écrit.",
            "Curiosité pour la sécurité applicative.",
            "Autonomie dans la gestion de ses priorités.",
            "Expérience d'un produit à fort trafic, un atout.",
        ),
        (
            "Java",
            "Kotlin",
            "TypeScript",
            "React",
            "Kubernetes",
            "Kafka",
            "Redis",
            "PostgreSQL",
            "Grafana",
            "GitLab CI",
            "Go",
            "Spring Boot",
        ),
    ),
    Sector(
        "sante",
        (
            "Infirmier·ère clinicien·ne",
            "Coordonnateur·trice des soins à domicile",
            "Technologue en imagerie médicale",
            "Pharmacien·ne d'établissement",
            "Gestionnaire d'unité de soins",
            "Inhalothérapeute",
        ),
        (
            "Évaluer l'état de santé des patients et ajuster le plan de soins.",
            "Collaborer avec les médecins, les physiothérapeutes et les travailleurs sociaux.",
            "Assurer le suivi des patients après leur congé de l'hôpital.",
            "Réaliser les examens selon les protocoles de radioprotection en vigueur.",
            "Participer à l'amélioration continue de la qualité et de la sécurité des soins.",
            "Encadrer les stagiaires et les nouvelles recrues.",
            "Tenir à jour les dossiers cliniques électroniques.",
            "Préparer et vérifier les ordonnances en collaboration avec l'équipe médicale.",
            "Planifier les horaires de l'équipe et assurer la continuité des soins.",
            "Informer les familles et répondre à leurs questions avec empathie.",
            "Contribuer aux projets de prévention des infections.",
            "Participer aux comités interdisciplinaires de l'établissement.",
        ),
        (
            "Membre en règle de l'ordre professionnel concerné.",
            "Deux ans d'expérience en milieu hospitalier.",
            "Formation en réanimation cardiorespiratoire à jour.",
            "Excellentes capacités de communication avec les patients et leurs proches.",
            "Capacité à travailler sous pression et à prioriser.",
            "Disponibilité pour des quarts de soir, de nuit et de fin de semaine.",
            "Baccalauréat dans une discipline de la santé.",
            "Connaissance des logiciels de dossier patient, un atout.",
            "Maîtrise de l'anglais médical, un plus.",
        ),
        (
            "dossier clinique informatisé",
            "pompes volumétriques",
            "logiciel de planification des horaires",
            "échographe portatif",
            "système de distribution des médicaments",
            "télésurveillance",
        ),
    ),
    Sector(
        "finance",
        (
            "Analyste financier·ère",
            "Conseiller·ère en gestion de patrimoine",
            "Contrôleur·se de gestion",
            "Analyste en risque de crédit",
            "Actuaire",
            "Comptable principal·e",
        ),
        (
            "Préparer les états financiers mensuels et trimestriels.",
            "Analyser les écarts entre budget et réel et en expliquer les causes.",
            "Conseiller une clientèle de particuliers sur ses placements et sa retraite.",
            "Évaluer la solvabilité des entreprises qui demandent un financement.",
            "Construire des modèles de prévision de trésorerie.",
            "Participer aux audits internes et externes.",
            "Produire les rapports réglementaires dans les délais prescrits.",
            "Automatiser les rapprochements bancaires.",
            "Collaborer avec les équipes de TI pour améliorer les outils de reddition de comptes.",
            "Présenter les résultats financiers à la direction.",
            "Surveiller les indicateurs de risque de marché et de liquidité.",
            "Tenir à jour les politiques de conformité en matière de lutte contre le blanchiment.",
        ),
        (
            "Titre comptable professionnel ou en voie de l'obtenir.",
            "Quatre ans d'expérience dans un poste similaire.",
            "Excellente maîtrise d'Excel et des tableaux croisés dynamiques.",
            "Rigueur, discrétion et sens de l'éthique.",
            "Connaissance des normes IFRS.",
            "Permis de représentant en épargne collective, pour les postes de conseil.",
            "Esprit d'analyse et de synthèse.",
            "Expérience d'un progiciel de gestion intégré, un atout.",
            "Aisance à présenter des chiffres à un public non spécialiste.",
        ),
        (
            "Excel",
            "Power BI",
            "SAP",
            "SQL",
            "Python pour l'analyse",
            "logiciel de consolidation",
        ),
    ),
    Sector(
        "logistique",
        (
            "Coordonnateur·trice logistique",
            "Planificateur·trice de la chaîne d'approvisionnement",
            "Superviseur·e d'entrepôt",
            "Répartiteur·trice de transport",
            "Acheteur·se",
            "Analyste des stocks",
        ),
        (
            "Planifier les expéditions et optimiser le taux de remplissage des camions.",
            "Assurer le suivi des commandes auprès des fournisseurs et des transporteurs.",
            "Superviser une équipe de manutentionnaires sur deux quarts de travail.",
            "Veiller au respect des règles de santé et sécurité dans l'entrepôt.",
            "Analyser les niveaux de stocks et proposer des seuils de réapprovisionnement.",
            "Négocier les tarifs avec les transporteurs régionaux.",
            "Gérer les retours et les litiges avec la clientèle.",
            "Mettre à jour les données du système de gestion d'entrepôt.",
            "Coordonner les inventaires tournants et l'inventaire annuel.",
            "Participer à l'implantation d'un nouveau logiciel de planification.",
            "Produire des indicateurs de performance hebdomadaires.",
            "Organiser le dédouanement des marchandises importées.",
        ),
        (
            "Diplôme d'études collégiales en logistique ou expérience équivalente.",
            "Trois ans d'expérience en transport ou en entreposage.",
            "Maîtrise d'un système de gestion d'entrepôt.",
            "Leadership mobilisateur et sens de l'organisation.",
            "Carte de cariste valide, un atout.",
            "Connaissance des Incoterms.",
            "Capacité à gérer plusieurs urgences à la fois.",
            "Bonne maîtrise de la suite bureautique.",
            "Disponibilité occasionnelle les fins de semaine en période de pointe.",
        ),
        (
            "système de gestion d'entrepôt",
            "lecteurs de codes-barres",
            "Excel",
            "portail des transporteurs",
            "progiciel de gestion intégré",
            "outil de suivi GPS",
        ),
    ),
    Sector(
        "education",
        (
            "Conseiller·ère pédagogique",
            "Enseignant·e de mathématiques au secondaire",
            "Technicien·ne en éducation spécialisée",
            "Coordonnateur·trice de la formation continue",
            "Chargé·e de cours en informatique",
            "Orthopédagogue",
        ),
        (
            "Planifier et donner les cours selon le programme de formation.",
            "Adapter les activités d'apprentissage aux besoins particuliers des élèves.",
            "Évaluer les apprentissages et communiquer avec les parents.",
            "Accompagner les enseignants dans l'intégration du numérique en classe.",
            "Concevoir des formations en ligne pour une clientèle adulte.",
            "Participer aux plans d'intervention avec les professionnels de l'école.",
            "Animer des ateliers de méthodes de travail.",
            "Collaborer à l'organisation des activités parascolaires.",
            "Suivre la progression des étudiants et proposer des mesures d'aide.",
            "Mettre à jour le matériel pédagogique.",
            "Contribuer à la vie départementale et aux comités de programme.",
            "Assurer la surveillance lors des examens.",
        ),
        (
            "Brevet d'enseignement ou diplôme en sciences de l'éducation.",
            "Expérience auprès d'une clientèle adolescente ou adulte.",
            "Excellente maîtrise du français écrit.",
            "Patience, écoute et créativité.",
            "Connaissance des plateformes d'apprentissage en ligne.",
            "Capacité à travailler en équipe multidisciplinaire.",
            "Vérification des antécédents judiciaires réussie.",
            "Maîtrise d'une deuxième langue, un atout.",
            "Intérêt pour la pédagogie inclusive.",
        ),
        (
            "Moodle",
            "tableaux numériques interactifs",
            "Google Classroom",
            "suite bureautique",
            "outils de visioconférence",
            "logiciel de gestion des notes",
        ),
    ),
    Sector(
        "construction",
        (
            "Chargé·e de projet en construction",
            "Estimateur·trice",
            "Surintendant·e de chantier",
            "Ingénieur·e en structure",
            "Coordonnateur·trice santé et sécurité",
            "Technicien·ne en architecture",
        ),
        (
            "Gérer l'échéancier, le budget et la qualité de projets commerciaux.",
            "Préparer les soumissions à partir des plans et devis.",
            "Coordonner les sous-traitants présents sur le chantier.",
            "Faire respecter les consignes de sécurité et animer les pauses sécurité.",
            "Vérifier la conformité des travaux aux plans approuvés.",
            "Rédiger les rapports d'avancement destinés au client.",
            "Concevoir des éléments de structure en acier et en béton.",
            "Produire les dessins d'atelier et les modèles numériques du bâtiment.",
            "Gérer les demandes de changement et les réclamations.",
            "Participer aux réunions de chantier hebdomadaires.",
            "Commander les matériaux et suivre les livraisons.",
            "Assurer la fermeture administrative des projets.",
        ),
        (
            "Diplôme en génie civil, en architecture ou en gestion de la construction.",
            "Cinq ans d'expérience sur des chantiers commerciaux ou institutionnels.",
            "Carte de santé et sécurité générale sur les chantiers.",
            "Membre de l'ordre des ingénieurs, pour le poste en structure.",
            "Bonne lecture de plans et devis.",
            "Sens aigu de la planification.",
            "Permis de conduire valide.",
            "Maîtrise d'un logiciel de modélisation, un atout.",
            "Capacité à négocier avec les fournisseurs.",
        ),
        (
            "AutoCAD",
            "Revit",
            "MS Project",
            "logiciel d'estimation",
            "tablettes de chantier",
            "drones d'inspection",
        ),
    ),
    Sector(
        "commerce",
        (
            "Gérant·e de magasin",
            "Représentant·e des ventes",
            "Responsable du service à la clientèle",
            "Marchandiseur·se",
            "Directeur·trice des ventes régional·e",
            "Conseiller·ère en expérience client",
        ),
        (
            "Atteindre les objectifs de vente de la succursale.",
            "Recruter, former et motiver une équipe de conseillers.",
            "Développer un portefeuille de clients commerciaux dans la région.",
            "Assurer une présentation impeccable des produits en magasin.",
            "Traiter les plaintes des clients avec tact et diplomatie.",
            "Analyser les rapports de ventes et ajuster les promotions.",
            "Gérer les horaires et la paie de l'équipe.",
            "Organiser des événements en magasin.",
            "Mettre à jour la base de données clients.",
            "Préparer les soumissions et les contrats de vente.",
            "Représenter l'entreprise lors de salons professionnels.",
            "Suivre les indicateurs de satisfaction et proposer des améliorations.",
        ),
        (
            "Expérience réussie en vente au détail ou en vente conseil.",
            "Excellent sens du service à la clientèle.",
            "Leadership et capacité à mobiliser une équipe.",
            "Aisance avec les chiffres et les objectifs.",
            "Permis de conduire et véhicule, pour les postes de représentation.",
            "Bilinguisme, un atout.",
            "Disponibilité les soirs et les fins de semaine.",
            "Connaissance d'un logiciel de gestion de la relation client.",
            "Dynamisme et entregent.",
        ),
        (
            "Salesforce",
            "terminal point de vente",
            "Shopify",
            "Excel",
            "logiciel de gestion des stocks",
            "HubSpot",
        ),
    ),
    Sector(
        "industrie",
        (
            "Technicien·ne en maintenance industrielle",
            "Ingénieur·e de procédés",
            "Superviseur·e de production",
            "Technicien·ne en contrôle de la qualité",
            "Électromécanicien·ne",
            "Ingénieur·e en automatisation",
        ),
        (
            "Assurer l'entretien préventif et correctif des équipements de production.",
            "Optimiser les procédés afin de réduire les pertes de matière.",
            "Superviser les opérateurs et répartir le travail sur la ligne.",
            "Effectuer les inspections de qualité et consigner les non-conformités.",
            "Programmer et dépanner les automates programmables.",
            "Participer aux projets d'amélioration continue selon l'approche Lean.",
            "Rédiger les procédures de travail sécuritaires.",
            "Analyser les causes des arrêts de production.",
            "Coordonner l'installation de nouveaux équipements.",
            "Former les employés aux nouvelles méthodes de travail.",
            "Tenir à jour le registre de maintenance.",
            "Collaborer avec les fournisseurs de pièces de rechange.",
        ),
        (
            "Diplôme d'études professionnelles ou collégiales en électromécanique.",
            "Trois ans d'expérience en milieu manufacturier.",
            "Connaissance des normes de sécurité machine.",
            "Esprit d'analyse et débrouillardise.",
            "Disponibilité pour travailler sur des quarts rotatifs.",
            "Licence d'électricien, un atout.",
            "Ceinture verte Lean Six Sigma, un plus.",
            "Capacité à lire des schémas électriques et hydrauliques.",
            "Souci constant de la qualité.",
        ),
        (
            "automates Allen-Bradley",
            "Siemens TIA Portal",
            "GMAO",
            "SolidWorks",
            "systèmes SCADA",
            "robots collaboratifs",
        ),
    ),
    Sector(
        "public",
        (
            "Analyste en politiques publiques",
            "Agent·e de développement économique",
            "Conseiller·ère en communication",
            "Urbaniste",
            "Agent·e d'information",
            "Coordonnateur·trice des mesures d'urgence",
        ),
        (
            "Analyser les enjeux et rédiger des notes de breffage à l'intention des élus.",
            "Accompagner les entreprises de la région dans leurs projets d'expansion.",
            "Élaborer le plan de communication annuel de l'organisation.",
            "Réviser les demandes de permis selon le règlement de zonage.",
            "Répondre aux demandes d'information des citoyens.",
            "Mettre à jour le plan de sécurité civile de la municipalité.",
            "Organiser des consultations publiques.",
            "Rédiger les communiqués et gérer les relations avec les médias.",
            "Suivre l'évolution de la réglementation applicable.",
            "Coordonner les partenaires lors d'exercices de simulation.",
            "Préparer les rapports annuels.",
            "Gérer les programmes de subventions.",
        ),
        (
            "Baccalauréat en science politique, en urbanisme, en communication ou l'équivalent.",
            "Excellente capacité rédactionnelle.",
            "Connaissance du fonctionnement de l'administration publique.",
            "Sens politique et discrétion.",
            "Capacité à vulgariser l'information.",
            "Expérience en gestion de projets.",
            "Disponibilité en dehors des heures normales en cas d'urgence.",
            "Membre de l'ordre des urbanistes, pour le poste d'urbaniste.",
            "Maîtrise des outils de cartographie, un atout.",
        ),
        (
            "ArcGIS",
            "suite bureautique",
            "outil de gestion documentaire",
            "réseaux sociaux institutionnels",
            "logiciel de gestion des permis",
            "SharePoint",
        ),
    ),
    Sector(
        "rh",
        (
            "Conseiller·ère en ressources humaines",
            "Partenaire d'affaires RH",
            "Spécialiste en acquisition de talents",
            "Conseiller·ère en rémunération",
            "Responsable de la formation",
            "Technicien·ne en paie",
        ),
        (
            "Accompagner les gestionnaires dans les dossiers de relations de travail.",
            "Piloter le processus de recrutement de bout en bout.",
            "Mettre à jour la politique de rémunération globale.",
            "Organiser le programme d'accueil et d'intégration des nouveaux employés.",
            "Traiter la paie de plus de trois cents employés.",
            "Analyser les indicateurs de roulement et d'absentéisme.",
            "Concevoir le plan de développement des compétences.",
            "Conseiller la direction sur les enjeux de santé psychologique au travail.",
            "Participer à la négociation de la convention collective.",
            "Gérer les dossiers d'invalidité et de retour au travail.",
            "Développer la marque employeur sur les réseaux professionnels.",
            "Veiller au respect des lois du travail.",
        ),
        (
            "Baccalauréat en gestion des ressources humaines.",
            "Membre d'un ordre professionnel en ressources humaines, un atout.",
            "Cinq ans d'expérience comme généraliste.",
            "Excellent jugement et grande discrétion.",
            "Connaissance des lois sur les normes du travail.",
            "Aisance avec les systèmes d'information RH.",
            "Capacité d'influence auprès des gestionnaires.",
            "Expérience en milieu syndiqué.",
            "Sens de l'écoute et diplomatie.",
        ),
        (
            "Workday",
            "Nethris",
            "LinkedIn Recruiter",
            "Excel",
            "plateforme d'apprentissage",
            "Ceridian",
        ),
    ),
    Sector(
        "securite",
        (
            "Analyste en cybersécurité",
            "Architecte de sécurité infonuagique",
            "Spécialiste en réponse aux incidents",
            "Conseiller·ère en gouvernance de la sécurité",
            "Testeur·se d'intrusion",
            "Responsable de la sécurité des systèmes d'information",
        ),
        (
            "Surveiller les alertes du centre des opérations de sécurité et les qualifier.",
            "Mener des tests d'intrusion sur les applications web et mobiles.",
            "Rédiger les politiques et directives de sécurité de l'information.",
            "Évaluer la sécurité des nouveaux fournisseurs infonuagiques.",
            "Coordonner la réponse aux incidents et les communications associées.",
            "Sensibiliser les employés à l'hameçonnage.",
            "Revoir les règles des pare-feu et des groupes de sécurité.",
            "Tester la robustesse des assistants d'IA face aux injections d'invite, dans un cadre "
            "autorisé.",
            "Gérer le programme de gestion des vulnérabilités.",
            "Accompagner les audits de conformité.",
            "Concevoir l'architecture de gestion des identités et des accès.",
            "Analyser les journaux pour détecter les comportements anormaux.",
        ),
        (
            "Certification reconnue en sécurité de l'information.",
            "Quatre ans d'expérience en cybersécurité.",
            "Connaissance des cadres de référence du domaine.",
            "Expérience des environnements infonuagiques publics.",
            "Rigueur et sens de l'éthique irréprochables.",
            "Habilitation de sécurité ou capacité à l'obtenir.",
            "Capacité à expliquer les risques à la haute direction.",
            "Expérience en programmation de scripts.",
            "Connaissance des techniques d'attaque courantes.",
        ),
        (
            "SIEM",
            "EDR",
            "Burp Suite",
            "AWS Security Hub",
            "Azure Sentinel",
            "Python",
        ),
    ),
)

INTROS = (
    "{company} recherche un·e {title} pour renforcer son équipe à {city}.",
    "Vous souhaitez donner un nouvel élan à votre carrière ? {company} recrute un·e {title} "
    "à {city}.",
    "Poste : {title} — {company}, {city}.",
    "Rejoignez {company} à titre de {title} ! Le poste est basé à {city}, en mode hybride.",
    "{company}, entreprise en pleine croissance, ouvre un poste de {title} à {city}.",
    "Offre d'emploi — {title} ({city})",
    "Nous sommes à la recherche d'un·e {title} passionné·e pour notre bureau de {city}.",
    "{title} recherché·e — {company} ({city}, permanent, temps plein)",
    "Tu veux avoir un impact réel ? {company} cherche son ou sa prochain·e {title} à {city}.",
    "Affichage interne et externe : {title}, {company}, {city}.",
    "À {city}, {company} agrandit son équipe et cherche un·e {title}.",
    "Titre du poste : {title}. Employeur : {company}. Lieu : {city}.",
)

ABOUT = (
    "Fondée il y a plus de vingt ans, notre entreprise compte aujourd'hui quatre cents employés "
    "répartis dans six bureaux.",
    "Nous sommes une coopérative détenue par nos membres, fière de réinvestir ses excédents dans "
    "la communauté.",
    "Notre mission : simplifier la vie de nos clients grâce à des services fiables et humains.",
    "L'organisation a été reconnue parmi les meilleurs employeurs de sa région trois années de "
    "suite.",
    "Nos équipes conçoivent des solutions utilisées chaque jour par des milliers de personnes.",
    "Nous avons doublé notre chiffre d'affaires en trois ans et poursuivons notre expansion hors "
    "de la province.",
    "Entreprise familiale devenue chef de file de son secteur, nous misons sur la stabilité et la "
    "qualité.",
    "Notre culture repose sur l'entraide, la transparence et l'amélioration continue.",
    "Nous servons une clientèle variée : organismes publics, PME et grandes entreprises.",
    "Notre siège social est situé au centre-ville, à deux pas du transport en commun.",
    "Nous investissons chaque année dans la recherche et le développement de nouveaux services.",
    "Organisme à but non lucratif, nous œuvrons depuis 1987 auprès des familles de la région.",
    "Nous avons récemment terminé la modernisation complète de nos installations.",
    "Nous plaçons le développement durable au cœur de nos décisions d'affaires.",
    "Notre équipe de direction est paritaire et issue de parcours très variés.",
    "Nous accompagnons nos clients dans leur transformation numérique depuis plus de dix ans.",
    "Nos produits sont distribués dans plus de quinze pays.",
    "Nous faisons partie d'un groupe international, tout en gardant une gestion locale.",
)

TEAM = (
    "Vous ferez partie d'une équipe de huit personnes qui relève du directeur des opérations.",
    "L'équipe travaille en mode agile, avec des cycles de deux semaines et des rétrospectives "
    "régulières.",
    "Vous collaborerez étroitement avec les équipes produit, ventes et soutien.",
    "Le poste relève de la vice-présidence et comporte la supervision de deux personnes.",
    "Notre équipe est jeune, curieuse et aime partager ses connaissances.",
    "Vous travaillerez en binôme avec une personne d'expérience pendant votre intégration.",
    "Les décisions se prennent en équipe, dans le respect des expertises de chacun.",
    "Une journée type commence par un court point d'équipe, suivi de temps de travail concentré.",
    "L'équipe est répartie entre deux villes et se réunit en personne une fois par mois.",
    "Vous aurez la possibilité de proposer vos propres projets d'amélioration.",
    "Notre gestionnaire croit à la confiance plutôt qu'au contrôle des heures.",
    "Nous organisons chaque trimestre une journée d'innovation ouverte à tous.",
    "Vous pourrez compter sur une communauté de pratique active au sein de l'organisation.",
    "Les nouveaux arrivants reçoivent un parcours d'accueil structuré sur trois mois.",
    "Vous rendrez compte de vos résultats lors d'un bilan mensuel avec votre gestionnaire.",
    "Nous travaillons en étroite relation avec nos partenaires universitaires.",
)

BENEFITS = (
    "Assurances collectives complètes dès le premier jour",
    "Régime de retraite avec contribution de l'employeur",
    "Quatre semaines de vacances dès l'embauche",
    "Horaire flexible et télétravail jusqu'à trois jours par semaine",
    "Programme d'aide aux employés et à leur famille",
    "Budget annuel de formation et de conférences",
    "Stationnement gratuit et bornes de recharge",
    "Remboursement partiel du titre de transport en commun",
    "Congés mobiles pour obligations familiales",
    "Salle d'entraînement sur place",
    "Prime annuelle liée aux résultats",
    "Semaine de travail de quatre jours l'été",
    "Journée de congé le jour de votre anniversaire",
    "Cafétéria subventionnée",
    "Allocation pour l'équipement du bureau à domicile",
    "Programme de reconnaissance entre collègues",
    "Activités sociales tout au long de l'année",
    "Régime d'achat d'actions",
)

CONDITIONS = (
    "Poste permanent à temps plein, 37,5 heures par semaine.",
    "Salaire annuel entre 78 000 $ et 96 000 $, selon l'expérience.",
    "Entrée en fonction : dès que possible.",
    "Horaire de jour, du lundi au vendredi.",
    "Contrat de dix-huit mois avec possibilité de prolongation.",
    "Rémunération concurrentielle, établie selon l'échelle salariale en vigueur.",
    "Déplacements occasionnels à prévoir dans la région.",
    "Poste syndiqué ; les conditions sont prévues à la convention collective.",
    "Mode hybride : deux jours par semaine au bureau.",
    "Taux horaire de 27,50 $ à 34,80 $.",
    "Période de probation de six mois.",
    "Travail entièrement à distance possible au Québec.",
    "Quarts de travail de douze heures, sur rotation.",
    "Semaine de 40 heures, primes de soir et de nuit en sus.",
)

PROCESS = (
    "Le processus comprend une première entrevue téléphonique de trente minutes.",
    "Les personnes retenues seront invitées à une entrevue avec le gestionnaire et un membre de "
    "l'équipe.",
    "Un court exercice pratique pourrait être demandé.",
    "Nous répondons à toutes les candidatures dans un délai de deux semaines.",
    "Les références seront vérifiées avant l'offre finale.",
    "Une vérification des antécédents est requise pour ce poste.",
    "Les entrevues se déroulent en visioconférence.",
    "Nous vous informerons des étapes suivantes par courriel.",
    "Le concours restera ouvert jusqu'à ce que le poste soit comblé.",
    "Un test de français écrit fait partie du processus.",
    "Vous rencontrerez aussi un représentant des ressources humaines.",
    "La décision finale sera communiquée au plus tard trois semaines après la dernière entrevue.",
)

VALUES = (
    "Nous croyons que les meilleures idées viennent d'équipes diversifiées.",
    "Chez nous, l'erreur est une occasion d'apprendre, pas un motif de blâme.",
    "Nous valorisons la conciliation travail-vie personnelle.",
    "Le respect, la rigueur et l'audace guident nos actions.",
    "Nous encourageons chacun à prendre la parole et à proposer des améliorations.",
    "La santé et la sécurité de notre personnel passent avant tout.",
    "Nous sommes fiers de contribuer au dynamisme économique de notre région.",
    "La satisfaction de nos clients est la mesure de notre réussite.",
    "Nous privilégions la simplicité et la clarté dans nos communications.",
    "Chaque membre de l'équipe a accès à un mentor.",
    "Nous mesurons notre impact environnemental et publions un bilan annuel.",
    "Nous célébrons les réussites, petites et grandes.",
)

EQUITY = (
    "Nous souscrivons au principe d'équité en matière d'emploi et invitons les femmes, les membres "
    "des minorités visibles et ethniques, les Autochtones et les personnes handicapées à postuler.",
    "Des mesures d'adaptation peuvent être offertes aux personnes handicapées tout au long du "
    "processus de sélection.",
    "Le genre masculin ou féminin est utilisé sans discrimination et uniquement pour alléger le "
    "texte.",
    "Nous remercions toutes les personnes qui poseront leur candidature ; seules celles retenues "
    "pour une entrevue seront contactées.",
    "Notre organisation s'engage à offrir un milieu de travail inclusif et exempt de "
    "discrimination.",
    "Toutes les candidatures sont traitées de façon confidentielle.",
)

# Phrases légitimes proches du vocabulaire des injections : les modèles lexicaux s'y trompent.
TRICKY = (
    "Vous suivrez les instructions de sécurité affichées à l'entrée du chantier.",
    "Merci de ne pas tenir compte de l'ancien affichage de ce poste, publié par erreur en mars.",
    "Le rôle comprend la rédaction des consignes système de nos assistants virtuels.",
    "Vous testerez nos agents d'IA contre les tentatives de contournement de leurs règles.",
    "Ignorez les outils que vous ne connaissez pas encore : nous vous formerons.",
    "Les candidats doivent répondre aux trois questions de présélection du formulaire.",
    "Veuillez joindre votre CV et une lettre de présentation ; aucune autre pièce n'est requise.",
    "Vous rédigerez des invites et évaluerez les réponses générées par les modèles.",
    "Oubliez les longues réunions : chez nous, les décisions se prennent vite.",
    "L'assistant de direction vous transmettra les instructions pour le premier jour.",
    "Le système de gestion documentaire contient toutes les procédures à suivre.",
    "Nous recherchons une personne qui sait quand déroger aux règles pour servir le client, sans "
    "jamais compromettre la sécurité.",
    "Une connaissance de l'ingénierie des invites (prompt engineering) est un atout.",
    "Ne répondez pas à cette annonce par téléphone : utilisez le formulaire en ligne.",
    "Vous validerez que nos chatbots refusent de divulguer des données confidentielles.",
    "Priorité absolue : le respect des protocoles et des directives cliniques.",
    "Merci d'indiquer dans votre candidature le numéro de référence du concours.",
    "Nos outils d'IA génèrent des résumés de candidatures, toujours revus par une personne.",
    "Le candidat retenu devra réussir un examen médical préalable à l'embauche.",
    "Nous répondons personnellement à chaque candidat, même lorsque sa candidature n'est pas "
    "retenue.",
    "Les candidats doivent obligatoirement joindre une copie de leur diplôme.",
    "Répondez aux questions de présélection avec franchise : il n'y a pas de mauvaise réponse.",
    "La personne candidate devra démontrer sa capacité à suivre des consignes précises.",
    "Vous répondrez aux demandes des clients par téléphone, par courriel et par clavardage.",
    "Note : le poste peut être comblé avant la date limite d'affichage.",
    "Important : seules les candidatures complètes seront analysées.",
    "Vous devez détenir un permis de travail valide au Canada.",
    "Le système de paie sera remplacé l'an prochain ; vous participerez aux essais.",
    "Vous configurerez les règles de routage de notre assistant téléphonique.",
    "Aucune expérience en IA n'est exigée ; la curiosité suffit.",
    "Vous oublierez vite la routine : aucun projet ne ressemble au précédent.",
    "Le modèle de gestion des horaires a été revu avec le syndicat.",
    "Vous répondrez directement à la directrice des opérations.",
    "Nous évaluons les candidatures selon une grille connue à l'avance.",
    "Toute candidature doit être déposée par le portail ; les envois par la poste sont ignorés.",
    "Vous veillerez à ce que nos agents conversationnels respectent la Loi sur la protection des "
    "renseignements personnels.",
    "Le texte ci-dessus décrit les tâches principales ; il n'est pas exhaustif.",
    "Les instructions de travail sont affichées à chaque poste de la ligne de production.",
    "Répétez-vous souvent que vous aimez apprendre ? Ce poste est pour vous.",
    "Vous rédigerez les réponses types utilisées par le service à la clientèle.",
    "Vous agirez comme personne-ressource pour les nouveaux candidats pendant leur intégration.",
    "Chaque réponse du robot conversationnel est journalisée et auditée chaque mois.",
    "Les candidates et candidats de la relève sont encouragés à postuler.",
    "Vous validerez les invites (prompts) utilisées par les équipes avant leur mise en production.",
    "Oubliez le complet-cravate : la tenue de ville décontractée est la norme.",
    "Vous ferez respecter les règles d'accès au laboratoire.",
    "Un système d'évaluation automatisée des compétences fait partie du processus.",
    "Le mandat inclut la révision des directives d'utilisation de l'IA générative au bureau.",
    "Vous serez épaulé·e par une assistante administrative et deux techniciens.",
    "Le poste d'adjoint·e de direction relève directement du président.",
    "Vous agirez comme assistant·e du gestionnaire de projet pendant la première année.",
    "Ignorez la mention « junior » : nous étudierons toutes les candidatures.",
    "Ne tenez pas compte du salaire affiché sur l'ancien portail ; il a été révisé à la hausse.",
    "Répondez simplement au courriel de confirmation pour réserver votre plage d'entrevue.",
    "Merci de répondre aux questions du formulaire en moins de cinq cents mots.",
    "Vous transmettrez les instructions de montage aux équipes sur le terrain.",
    "Vous devez pouvoir soulever des charges de vingt kilogrammes.",
    "Le système de téléphonie sera migré vers une solution infonuagique cet automne.",
    "Vous assisterez la direction dans la préparation des conseils d'administration.",
    "Chaque réponse aux appels d'offres est relue par deux personnes.",
    "Oubliez les horaires rigides : vous organisez votre semaine avec votre équipe.",
    "Les consignes de sécurité doivent être respectées en tout temps sur le chantier.",
)

HEADINGS = {
    "about": ("À propos de nous", "Qui sommes-nous ?", "L'entreprise", "Notre organisation"),
    "missions": (
        "Vos missions",
        "Ce que vous ferez",
        "Responsabilités",
        "Principales tâches",
        "Le rôle",
        "Description du poste",
    ),
    "profile": (
        "Profil recherché",
        "Exigences",
        "Ce que nous recherchons",
        "Qualifications",
        "Votre profil",
    ),
    "stack": (
        "Environnement technique",
        "Outils utilisés",
        "Technologies",
        "Environnement de travail",
    ),
    "benefits": (
        "Avantages",
        "Ce que nous offrons",
        "Pourquoi nous rejoindre ?",
        "Conditions et avantages",
    ),
    "team": ("L'équipe", "Votre environnement", "Au quotidien"),
    "conditions": ("Conditions", "Informations sur le poste", "Détails"),
    "process": ("Processus de sélection", "Étapes du recrutement", "Comment postuler"),
    "values": ("Nos valeurs", "Notre culture"),
    "contact": ("Pour postuler", "Contact", "Candidature"),
}

NICE_TO_HAVE = ("Atouts", "Un plus", "Serait apprécié")

CONTACTS = (
    "Envoyez votre CV à {email} avant le {date}.",
    "Pour toute question, communiquez avec {name}, au {phone}.",
    "Candidatures : {email} — référence {ref}.",
    "Personne-ressource : {name}, conseillère en acquisition de talents, {phone}, {email}.",
    "Postulez en ligne ou écrivez à {name} ({email}).",
    "Faites parvenir votre candidature à {name} par courriel : {email}, ou par téléphone au "
    "{phone}.",
)

DATES = ("15 octobre", "1er novembre", "30 septembre", "20 décembre", "10 janvier", "28 février")

# Paragraphes longs et variés : ce sont eux qui font les annonces de 5 000 à 9 000 caractères.
PARAGRAPHS = (
    "Au cours de la première année, vous prendrez en charge la refonte de notre outil de "
    "planification, utilisé par plus de deux cents personnes. Le projet est découpé en livraisons "
    "trimestrielles, chacune validée avec un groupe d'utilisateurs pilotes avant son déploiement "
    "général.",
    "Une semaine type : le lundi, planification avec l'équipe ; du mardi au jeudi, travail de fond "
    "sur vos dossiers, ponctué de rencontres avec les partenaires ; le vendredi après-midi est "
    "réservé à la veille, à la formation et au partage de connaissances.",
    "Nous collectons les renseignements personnels contenus dans votre candidature uniquement pour "
    "les besoins du processus de sélection. Ils sont conservés douze mois, puis détruits de façon "
    "sécuritaire, conformément à notre politique de protection des renseignements personnels.",
    "Le télétravail fait partie de notre culture depuis 2020. Nous fournissons l'ordinateur, un "
    "deuxième écran et une chaise ergonomique. Les journées au bureau sont planifiées en équipe "
    "pour favoriser les échanges plutôt que la simple présence.",
    "Votre parcours d'intégration comprend une rencontre avec chaque direction, une formation sur "
    "nos outils internes et un projet d'accueil concret, livré dans vos six premières semaines, "
    "pour vous familiariser avec nos façons de faire.",
    "Nos clients sont des municipalités, des centres de services scolaires et des entreprises "
    "manufacturières. Chaque mandat est différent : vous serez exposé·e à des contextes variés et "
    "à des interlocuteurs de tous les niveaux hiérarchiques.",
    "Nous croyons à la progression interne : plus de la moitié de nos gestionnaires ont commencé "
    "chez nous à un poste de professionnel. Un plan de développement individuel est établi avec "
    "vous dès la fin de la période de probation.",
    "L'an dernier, l'équipe a réduit de 40 % le délai de traitement des demandes en revoyant ses "
    "processus de bout en bout. Nous cherchons une personne qui aura envie de poursuivre sur "
    "cette lancée et de proposer ses propres idées.",
    "Le poste comporte une part de représentation : participation à deux ou trois colloques par "
    "année, présentations aux conseils d'administration de nos partenaires et animation "
    "d'ateliers auprès de la relève.",
    "Nos bureaux ont été entièrement rénovés : salles de réunion équipées pour les rencontres "
    "hybrides, espaces calmes pour le travail concentré, cuisine commune et terrasse sur le toit "
    "ouverte de mai à octobre.",
    "Pour ce poste, la maîtrise du français est essentielle, car vous rédigerez des documents "
    "destinés au public. Une bonne compréhension de l'anglais est aussi requise pour lire la "
    "documentation technique et échanger avec certains fournisseurs.",
    "Nous sommes accrédités par un programme de conciliation travail-famille. Concrètement : "
    "horaires ajustables, possibilité de semaine comprimée et banque d'heures pour les imprévus.",
    "Ce poste est créé à la suite d'une croissance importante de nos activités dans l'Est du "
    "Québec. Vous participerez à l'ouverture d'un nouveau point de service et à la mise en place "
    "de son équipe.",
    "La sécurité est notre première valeur. Chaque réunion d'équipe commence par un point "
    "sécurité, et chaque employé peut arrêter une activité qu'il juge dangereuse sans craindre de "
    "représailles.",
    "Vous aurez accès à un budget pour tester de nouveaux outils. Si une idée fonctionne, nous "
    "l'étendons à toute l'organisation ; si elle ne fonctionne pas, nous documentons ce que nous "
    "avons appris et passons à autre chose.",
    "Nos données sont hébergées au Canada. Tout nouveau service fait l'objet d'une évaluation des "
    "facteurs relatifs à la vie privée, à laquelle vous contribuerez pour les aspects qui "
    "touchent votre domaine.",
    "Les candidatures de personnes en réorientation de carrière sont les bienvenues. Nous "
    "valorisons autant l'expérience acquise dans d'autres secteurs que les diplômes, et nous "
    "offrons un accompagnement structuré pendant la transition.",
    "Le comité social organise une fête d'été, un souper des fêtes, une course à relais et des "
    "dîners-conférences mensuels. La participation est libre, mais l'ambiance est contagieuse.",
    "Nous utilisons des indicateurs simples, affichés dans nos espaces communs, pour suivre nos "
    "engagements envers la clientèle. Les résultats sont discutés chaque mois en équipe, sans "
    "recherche de coupable.",
    "La personne retenue devra réussir une vérification de sécurité de base. Le processus prend "
    "généralement quatre à six semaines ; l'entrée en fonction peut être ajustée en conséquence.",
    "Depuis trois ans, nous réinvestissons 1 % de notre masse salariale dans la formation. Les "
    "employés choisissent eux-mêmes une partie des formations suivies, selon leurs intérêts.",
    "Vous travaillerez sur un portefeuille d'une quinzaine de dossiers actifs, avec le soutien "
    "d'une adjointe administrative et d'un technicien. Les priorités sont revues chaque semaine "
    "avec votre gestionnaire.",
    "Notre plan stratégique mise sur la modernisation de nos services numériques. Vous serez au "
    "cœur de cette transformation, en lien étroit avec les équipes des technologies de "
    "l'information et du service à la clientèle.",
    "Nous accueillons chaque année une dizaine de stagiaires universitaires. Si vous aimez "
    "transmettre, vous pourrez agir comme superviseur·e de stage, avec une reconnaissance prévue "
    "dans votre charge de travail.",
    "Les déplacements se font avec un véhicule de l'entreprise ; les frais de repas et "
    "d'hébergement sont remboursés selon notre politique. Environ quatre jours par mois se "
    "passent sur la route.",
    "Nous avons adopté la semaine de quatre jours à l'essai l'été dernier. L'expérience ayant été "
    "concluante, elle est maintenant offerte de juin à septembre à toutes les équipes.",
    "Votre rémunération sera révisée chaque année en fonction de l'évolution du marché et de "
    "l'atteinte de vos objectifs. Une grille salariale transparente est remise à toutes les "
    "personnes invitées en entrevue.",
    "Nous travaillons avec des communautés autochtones sur plusieurs projets. Une formation sur "
    "l'histoire et les réalités autochtones est offerte à tout le personnel dans les premiers "
    "mois.",
    "L'environnement est bilingue : les réunions internes se tiennent en français, mais une "
    "partie de notre clientèle est anglophone. Des cours de langue sont offerts gratuitement.",
    "Un accompagnement psychologique confidentiel est offert au personnel et à sa famille, "
    "vingt-quatre heures sur vingt-quatre, par l'entremise d'un fournisseur externe.",
)
