# Vérificateur documentaire

Un script Python sans dépendance qui refuse ce qu'une documentation de projet ne devrait
pas contenir. Il tourne en intégration continue sans réseau, sans jeton et sans
résolution de dépendance : on le copie dans le dépôt, il s'exécute.

```bash
python3 verifier.py [chemin du dépôt]
```

## Ce qu'il refuse

1. un document sous `docs/` sans ligne de statut, en ligne 3, avec sa date au jour ;
2. un état hors d'une liste fermée ;
3. une ligne de statut à laquelle il manque un des quatre champs ;
4. un en-tête YAML concurrent de la ligne de statut ;
5. un fichier de contexte qui dépasse son seuil de lignes ;
6. un exemple canonique dont le chemin n'existe plus ;
7. un lien relatif mort ;
8. un fichier sensible suivi par git ;
9. une technologie citée par le fichier de contexte et absente du dépôt ;
10. un marqueur d'incomplétude resté en place.

## Pourquoi ces dix-là

Chacune vient d'un défaut observé dans un vrai dépôt, pas d'une liste de bonnes
intentions.

La neuvième, par exemple : un projet décrivait PostgreSQL et un système de migrations
dans son fichier de contexte, alors qu'il tournait sur SQLite sans couche d'abstraction.
Chaque session lisait cette description et raisonnait dessus. Rien ne confrontait le texte
au dépôt.

La dixième vient du même genre d'histoire. Un gabarit copié dans un projet y a laissé
soixante-neuf marqueurs à remplir, jamais remplis, pendant des mois. Un gabarit doit poser
des fichiers complets, ou signaler bruyamment ce qui manque. Ici l'incomplétude fait
échouer la vérification.

## Ce qu'il ne fait pas

Il ne lance ni lint, ni typage, ni tests : il les **appelle**, via les cibles que le projet
déclare dans `.claude/verifier.toml`. La frontière est nette et volontaire. Un script
partagé qui se met à juger le code finit par contredire les gardes du projet.

Il ne juge pas non plus la *qualité* d'un exemple canonique. Il vérifie que le chemin
existe. Qu'il soit un bon exemple reste une décision humaine.

## Réglages

Tout ce qui varie vit dans `.claude/verifier.toml` du projet, jamais dans ce fichier.
Voir `verifier.toml.exemple` : seuil de lignes, liste des états admis, cibles à déléguer,
technologies que la détection ne sait pas voir.

## Licence

MIT. Voir `LICENSE`.
