import discord
from discord.ext import commands
import json
import random
import os
import asyncio
from datetime import datetime, timedelta

# Configuration
  # Remplace par ton token
STARTING_BALANCE = 500

# Intents nécessaires
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Classe pour gérer la base de données
class Database:
    def __init__(self, filename='cazgino_data.json'):
        self.filename = filename
        self.data = self.load_data()
        self.stats_file = 'cazgino_stats.json'
        self.stats = self.load_stats()
    
    def load_data(self):
        if os.path.exists(self.filename):
            with open(self.filename, 'r') as f:
                return json.load(f)
        return {}
    
    def load_stats(self):
        if os.path.exists(self.stats_file):
            with open(self.stats_file, 'r') as f:
                return json.load(f)
        return {}
    
    def save_data(self):
        with open(self.filename, 'w') as f:
            json.dump(self.data, f, indent=4)
    
    def save_stats(self):
        with open(self.stats_file, 'w') as f:
            json.dump(self.stats, f, indent=4)
    
    def get_balance(self, user_id):
        user_id = str(user_id)
        if user_id not in self.data:
            self.data[user_id] = STARTING_BALANCE
            self.save_data()
        return self.data[user_id]
    
    def set_balance(self, user_id, amount):
        self.data[str(user_id)] = amount
        self.save_data()
    
    def add_balance(self, user_id, amount):
        current = self.get_balance(user_id)
        self.set_balance(user_id, current + amount)
    
    def add_game_played(self, user_id):
        """Enregistre qu'un joueur a participé à une partie"""
        user_id = str(user_id)
        if user_id not in self.stats:
            self.stats[user_id] = {'games_played': 0}
        self.stats[user_id]['games_played'] += 1
        self.save_stats()
    
    def has_played(self, user_id):
        """Vérifie si un joueur a déjà joué au moins une partie"""
        user_id = str(user_id)
        return user_id in self.stats and self.stats[user_id]['games_played'] > 0
    
    def get_leaderboard(self):
        """Retourne le classement des joueurs ayant joué au moins une partie"""
        eligible_players = {k: v for k, v in self.data.items() if self.has_played(k)}
        return sorted(eligible_players.items(), key=lambda x: x[1], reverse=True)

db = Database()

# Configuration de la roulette
ROULETTE_NUMBERS = {
    'rouge': [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36],
    'noir': [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35],
    'vert': [0]
}

# Partie de roulette en cours
active_roulette = None

# Jobs d'intérim en cours
active_jobs = {}

# Recettes possibles pour l'intérim
RECIPES = {
    'burger': {
        'name': '🍔 Burger',
        'steps': ['🥖', '🥩', '🧀', '🥬', '🍅', '🥖'],
        'emojis': ['🥖', '🥩', '🧀', '🥬', '🍅'],
        'reward': 5,
        'time_limit': 11
    },
    'pizza': {
        'name': '🍕 Pizza',
        'steps': ['🫓', '🍅', '🧀', '🍕'],
        'emojis': ['🫓', '🍅', '🧀', '🍕'],
        'reward': 6,
        'time_limit': 11
    },
    'tacos': {
        'name': '🌮 Tacos',
        'steps': ['🫓', '🥩', '🥬', '🧀', '🌶️'],
        'emojis': ['🫓', '🥩', '🥬', '🧀', '🌶️'],
        'reward': 5,
        'time_limit': 11
    },
    'sushi': {
        'name': '🍣 Sushi',
        'steps': ['🍚', '🐟', '🥢'],
        'emojis': ['🍚', '🐟', '🥢'],
        'reward': 7,
        'time_limit': 11
    },
    'salade': {
        'name': '🥗 Salade',
        'steps': ['🥬', '🍅', '🥒', '🥕'],
        'emojis': ['🥬', '🍅', '🥒', '🥕'],
        'reward': 5,
        'time_limit': 11
    }
}

class InterimJob:
    def __init__(self, user_id, recipe_key):
        self.user_id = user_id
        self.recipe = RECIPES[recipe_key]
        self.current_step = 0
        self.start_time = datetime.now()
        self.message = None
        self.completed = False
    
    def is_expired(self):
        return (datetime.now() - self.start_time).seconds > self.recipe['time_limit']
    
    def get_current_emoji(self):
        if self.current_step < len(self.recipe['steps']):
            return self.recipe['steps'][self.current_step]
        return None
    
    def next_step(self):
        self.current_step += 1
        return self.current_step >= len(self.recipe['steps'])

class RouletteGame:
    def __init__(self, ctx):
        self.ctx = ctx
        self.players = {}  # {user_id: {'bet': amount, 'choice': choice}}
        self.phase = 'joining'  # 'joining', 'betting', 'finished'
        self.result = None
        self.message = None
    
    def add_player(self, user_id):
        if user_id not in self.players:
            self.players[user_id] = {'bet': None, 'choice': None}
            return True
        return False
    
    def set_bet(self, user_id, choice, amount):
        if user_id in self.players:
            self.players[user_id]['bet'] = amount
            self.players[user_id]['choice'] = choice
            return True
        return False
    
    def spin(self):
        self.result = random.randint(0, 36)
        return self.result
    
    def get_color(self, number):
        if number in ROULETTE_NUMBERS['rouge']:
            return 'rouge'
        elif number in ROULETTE_NUMBERS['noir']:
            return 'noir'
        else:
            return 'vert'
    
    def calculate_winnings(self, choice, bet):
        # Vérifie d'abord si c'est un numéro exact
        if choice.isdigit() and choice == str(self.result):
            return bet * 36  # Numéro exact: x36
        # Couleur
        elif choice in ['rouge', 'noir'] and choice == self.get_color(self.result):
            return bet * 2  # Couleur: x2
        # Parité (pair/impair)
        elif choice == 'pair' and self.result != 0 and self.result % 2 == 0:
            return bet * 2
        elif choice == 'impair' and self.result % 2 == 1:
            return bet * 2
        # Moitiés
        elif choice == '1-18' and 1 <= self.result <= 18:
            return bet * 2
        elif choice == '19-36' and 19 <= self.result <= 36:
            return bet * 2
        # Aucun gain
        return 0

@bot.event
async def on_ready():
    print(f'✅ {bot.user} est connecté au Cazgino!')
    print(f'📊 {len(db.data)} joueurs enregistrés')

@bot.command(name='roulette')
async def roulette(ctx):
    """Lance une partie de roulette"""
    global active_roulette
    
    if active_roulette is not None:
        await ctx.send("❌ Une partie de roulette est déjà en cours !")
        return
    
    # Crée la partie
    active_roulette = RouletteGame(ctx)
    
    # Phase 1: Rejoindre (30 secondes)
    msg = await ctx.send(f"""
🎰 **CAZGINO - ROULETTE**

Une nouvelle partie de roulette commence !

**Phase 1: REJOINDRE LA PARTIE**
⏰ Vous avez **30 secondes** pour rejoindre !

Tapez `!join` pour participer !

Joueurs inscrits: **0**
    """)
    active_roulette.message = msg
    
    # Compte à rebours
    for i in range(30, 0, -10):
        await asyncio.sleep(10)
        if active_roulette is None:
            return
        player_count = len(active_roulette.players)
        await msg.edit(content=f"""
🎰 **CAZGINO - ROULETTE**

Une nouvelle partie de roulette commence !

**Phase 1: REJOINDRE LA PARTIE**
⏰ Il reste **{i} secondes** pour rejoindre !

Tapez `!join` pour participer !

Joueurs inscrits: **{player_count}**
        """)
    
    if len(active_roulette.players) == 0:
        await ctx.send("❌ Aucun joueur n'a rejoint ! Partie annulée.")
        active_roulette = None
        return
    
    # Phase 2: Miser (30 secondes)
    active_roulette.phase = 'betting'
    player_count = len(active_roulette.players)
    
    await ctx.send(f"""
🎰 **PHASE 2: PLACER VOS MISES**

**{player_count} joueurs** participent !

⏰ Vous avez **30 secondes** pour miser !

**Commande:** `!mise <choix> <montant>`

**Choix disponibles:**
• Numéro exact: `0` à `36` (gain x36)
• Couleur: `rouge` ou `noir` (gain x2)
• Parité: `pair` ou `impair` (gain x2)
• Moitié: `1-18` ou `19-36` (gain x2)

**Exemples:**
• `!mise rouge 50` - Mise 50€ sur rouge
• `!mise 17 100` - Mise 100€ sur le 17
• `!mise pair 25` - Mise 25€ sur pair
    """)
    
    # Compte à rebours pour les mises
    for i in range(30, 0, -10):
        await asyncio.sleep(10)
        if active_roulette is None:
            return
        bets_placed = sum(1 for p in active_roulette.players.values() if p['bet'] is not None)
        await ctx.send(f"⏰ **{i} secondes** restantes pour miser ! ({bets_placed}/{player_count} ont misé)")
    
    # Filtre les joueurs qui n'ont pas misé
    active_roulette.players = {k: v for k, v in active_roulette.players.items() if v['bet'] is not None}
    
    if len(active_roulette.players) == 0:
        await ctx.send("❌ Personne n'a misé ! Partie annulée.")
        active_roulette = None
        return
    
    # Phase 3: Lancement de la roulette avec animation
    result = active_roulette.spin()
    
    # Animation de la roulette
    animation_msg = await ctx.send("🎰 **LA ROULETTE TOURNE...**")
    
    # Génère une séquence de numéros aléatoires
    animation_numbers = [random.randint(0, 36) for _ in range(15)]
    # Ajoute le vrai résultat à la fin
    animation_numbers.append(result)
    
    for i, num in enumerate(animation_numbers):
        anim_color = active_roulette.get_color(num)
        anim_emoji = "🔴" if anim_color == "rouge" else "⚫" if anim_color == "noir" else "🟢"
        
        # Ralentit progressivement l'animation
        delay = 0.3 + (i * 0.1)
        
        if i < len(animation_numbers) - 1:
            # Pendant l'animation
            await animation_msg.edit(content=f"""
🎰 **LA ROULETTE TOURNE...**

{anim_emoji} **{num}** {anim_emoji}

{'▬' * 20}
            """)
        else:
            # Résultat final
            color = active_roulette.get_color(result)
            color_emoji = "🔴" if color == "rouge" else "⚫" if color == "noir" else "🟢"
            await animation_msg.edit(content=f"""
🎰 **RÉSULTAT DE LA ROULETTE**

{'=' * 20}
{color_emoji} **{result}** {color_emoji}
({color.upper()})
{'=' * 20}

Calcul des gains...
            """)
        
        await asyncio.sleep(delay)
    
    await asyncio.sleep(1)
    
    # Calcul des gains
    results_text = "🏆 **RÉSULTATS:**\n\n"
    winners = []
    losers = []
    
    for user_id, data in active_roulette.players.items():
        # Enregistre que le joueur a participé à une partie
        db.add_game_played(user_id)
        
        try:
            user = await bot.fetch_user(int(user_id))
            username = user.name
        except:
            username = f"Joueur {user_id}"
        
        choice = data['choice']
        bet = data['bet']
        winnings = active_roulette.calculate_winnings(choice, bet)
        
        if winnings > 0:
            profit = winnings - bet
            db.add_balance(user_id, winnings)
            winners.append(f"✅ **{username}** - Misé {bet}€ sur `{choice}` → **+{profit}€** (total: {winnings}€)")
        else:
            losers.append(f"❌ **{username}** - Misé {bet}€ sur `{choice}` → **Perdu**")
    
    if winners:
        results_text += "\n".join(winners) + "\n\n"
    if losers:
        results_text += "\n".join(losers)
    
    await ctx.send(results_text)
    
    # Réinitialise la partie
    active_roulette = None
    await ctx.send("✅ Partie terminée ! Vous pouvez relancer une nouvelle partie avec `!roulette`")

@bot.command(name='join', aliases=['rejoindre'])
async def join(ctx):
    """Rejoindre la partie de roulette en cours"""
    global active_roulette
    
    if active_roulette is None:
        await ctx.send("❌ Aucune partie de roulette en cours ! Lance-en une avec `!roulette`")
        return
    
    if active_roulette.phase != 'joining':
        await ctx.send("❌ La phase d'inscription est terminée !")
        return
    
    if active_roulette.add_player(ctx.author.id):
        await ctx.send(f"✅ {ctx.author.mention} a rejoint la partie !")
    else:
        await ctx.send(f"❌ {ctx.author.mention} tu es déjà inscrit !")

@bot.command(name='mise', aliases=['bet'])
async def mise(ctx, choix: str = None, montant: int = None):
    """Placer une mise - !mise <choix> <montant>"""
    global active_roulette
    
    if active_roulette is None:
        await ctx.send("❌ Aucune partie de roulette en cours !")
        return
    
    if active_roulette.phase != 'betting':
        await ctx.send("❌ Ce n'est pas le moment de miser !")
        return
    
    if ctx.author.id not in active_roulette.players:
        await ctx.send("❌ Tu n'as pas rejoint la partie !")
        return
    
    if active_roulette.players[ctx.author.id]['bet'] is not None:
        await ctx.send("❌ Tu as déjà misé ! Une seule mise par joueur.")
        return
    
    if choix is None or montant is None:
        await ctx.send("❌ Usage: `!mise <choix> <montant>` - Exemple: `!mise rouge 50`")
        return
    
    # Valide le choix
    choix = choix.lower()
    valid_choices = ['rouge', 'noir', 'pair', 'impair', '1-18', '19-36'] + [str(i) for i in range(37)]
    
    if choix not in valid_choices:
        await ctx.send(f"❌ Choix invalide ! Choisis parmi: {', '.join(valid_choices[:10])}...")
        return
    
    if montant <= 0:
        await ctx.send("❌ La mise doit être positive !")
        return
    
    balance = db.get_balance(ctx.author.id)
    if montant > balance:
        await ctx.send(f"❌ Tu n'as pas assez d'argent ! Ton solde: {balance}€")
        return
    
    # Débite la mise
    db.add_balance(ctx.author.id, -montant)
    active_roulette.set_bet(ctx.author.id, choix, montant)
    
    await ctx.send(f"✅ {ctx.author.mention} mise **{montant}€** sur `{choix}` !")

@bot.command(name='balance', aliases=['bal', 'argent'])
async def balance(ctx):
    """Affiche ton solde"""
    balance = db.get_balance(ctx.author.id)
    await ctx.send(f"💰 **{ctx.author.name}**, tu as **{balance}€**")

@bot.command(name='interim', aliases=['job', 'travail'])
async def interim(ctx):
    """Lance un job d'intérim pour gagner de l'argent"""
    
    if ctx.author.id in active_jobs:
        await ctx.send("❌ Tu as déjà un job en cours ! Termine-le d'abord.")
        return
    
    # Choisit une recette aléatoire
    recipe_key = random.choice(list(RECIPES.keys()))
    job = InterimJob(ctx.author.id, recipe_key)
    active_jobs[ctx.author.id] = job
    
    # Crée le message avec les instructions
    embed = discord.Embed(
        title="💼 INTÉRIM - Nouvelle commande !",
        description=f"**Prépare:** {job.recipe['name']}\n**Récompense:** {job.recipe['reward']}€\n**Temps limité:** {job.recipe['time_limit']}s",
        color=discord.Color.blue()
    )
    
    steps_display = " ➜ ".join(job.recipe['steps'])
    embed.add_field(
        name="📋 Étapes à suivre",
        value=steps_display,
        inline=False
    )
    
    embed.add_field(
        name="🎯 Instructions",
        value=f"Clique sur les réactions **dans l'ordre** pour préparer la commande !\nÉtape actuelle: **{job.get_current_emoji()}**",
        inline=False
    )
    
    embed.set_footer(text=f"Joueur: {ctx.author.name}")
    
    msg = await ctx.send(embed=embed)
    job.message = msg
    
    # Ajoute toutes les réactions nécessaires (mélangées pour la difficulté)
    emojis = job.recipe['emojis'].copy()
    random.shuffle(emojis)
    
    for emoji in emojis:
        await msg.add_reaction(emoji)
    
    # Vérifie le timeout avec une boucle qui s'arrête si le job est complété
    for _ in range(job.recipe['time_limit']):
        await asyncio.sleep(1)
        
        # Si le job n'existe plus (complété ou annulé), on arrête
        if ctx.author.id not in active_jobs:
            return
        
        # Si le job est marqué comme complété, on arrête
        if active_jobs[ctx.author.id].completed:
            return
    
    # Si on arrive ici, c'est que le temps est écoulé
    if ctx.author.id in active_jobs and not active_jobs[ctx.author.id].completed:
        await ctx.send(f"⏰ {ctx.author.mention} Temps écoulé ! Tu n'as pas terminé la commande à temps.")
        del active_jobs[ctx.author.id]
@bot.command(name='reroll', aliases=['relancer'])
async def reroll(ctx):
    balance = db.get_balance(ctx.author.id)
    if 200 > balance:
        await ctx.send(f"❌ Tu n'as pas assez d'argent ! Ton solde: {balance}€")
        return
    else:
        db.add_balance(ctx.author.id, -200)
        await ctx.send(f"✅ {ctx.author.mention} peut reroll une fois de plus !")

@bot.event
async def on_reaction_add(reaction, user):
    """Gère les réactions pour le jeu d'intérim"""
    
    # Ignore les réactions du bot
    if user.bot:
        return
    
    # Vérifie si l'utilisateur a un job actif
    if user.id not in active_jobs:
        return
    
    job = active_jobs[user.id]
    
    # Vérifie si c'est le bon message
    if reaction.message.id != job.message.id:
        return
    
    # Vérifie si le temps est écoulé
    if job.is_expired():
        await reaction.message.channel.send(f"⏰ {user.mention} Temps écoulé !")
        del active_jobs[user.id]
        return
    
    # Vérifie si c'est la bonne réaction
    expected_emoji = job.get_current_emoji()
    
    if str(reaction.emoji) == expected_emoji:
        # Bonne réaction !
        is_complete = job.next_step()
        
        if is_complete:
            # Commande terminée !
            job.completed = True
            reward = job.recipe['reward']
            db.add_balance(user.id, reward)
            new_balance = db.get_balance(user.id)
            
            embed = discord.Embed(
                title="✅ COMMANDE LIVRÉE !",
                description=f"{job.recipe['name']} préparé avec succès !",
                color=discord.Color.green()
            )
            embed.add_field(name="💰 Récompense", value=f"+{reward}€", inline=True)
            embed.add_field(name="💵 Nouveau solde", value=f"{new_balance}€", inline=True)
            
            await reaction.message.channel.send(f"{user.mention}", embed=embed)
            del active_jobs[user.id]
        else:
            # Passe à l'étape suivante
            next_emoji = job.get_current_emoji()
            progress = "✅ " * job.current_step + "⬜ " * (len(job.recipe['steps']) - job.current_step)
            
            embed = discord.Embed(
                title="💼 INTÉRIM - En cours...",
                description=f"**Prépare:** {job.recipe['name']}",
                color=discord.Color.orange()
            )
            embed.add_field(
                name="📊 Progression",
                value=progress,
                inline=False
            )
            embed.add_field(
                name="➡️ Prochaine étape",
                value=f"Clique sur **{next_emoji}**",
                inline=False
            )
            
            await reaction.message.edit(embed=embed)
    else:
        # Mauvaise réaction
        await reaction.message.channel.send(f"❌ {user.mention} Mauvais ingrédient ! Clique sur **{expected_emoji}**")
        await reaction.remove(user)

@bot.command(name='leaderboard', aliases=['classement', 'top'])
async def leaderboard(ctx):
    """Affiche le classement des plus riches (joueurs ayant participé à au moins 1 partie)"""
    
    leaderboard = db.get_leaderboard()[:10]
    
    if not leaderboard:
        await ctx.send("❌ Aucun joueur n'a encore participé à une partie !")
        return
    
    text = "🏆 **CAZGINO - CLASSEMENT DES PLUS RICHES**\n\n"
    medals = ['🥇', '🥈', '🥉']
    
    for i, (user_id, balance) in enumerate(leaderboard, 1):
        try:
            user = await bot.fetch_user(int(user_id))
            username = user.name
        except:
            username = f"Joueur {user_id}"
        
        medal = medals[i-1] if i <= 3 else f"**{i}.**"
        games_played = db.stats.get(user_id, {}).get('games_played', 0)
        text += f"{medal} {username} - **{balance}€** ({games_played} parties)\n"
    
    text += "\n_Seuls les joueurs ayant participé à au moins 1 partie apparaissent._"
    await ctx.send(text)

@bot.command(name='regles', aliases=['règles', 'regle', 'règle', 'rules'])
async def regles(ctx):
    """Affiche les règles de la roulette"""
    
    text = """
📜 **CAZGINO - RÈGLES**

🎰 **ROULETTE:**

**Objectif:** Parier sur le résultat de la roulette (0-36)

**Déroulement:**
• Phase 1 (30s): `!roulette` puis `!join` pour rejoindre
• Phase 2 (30s): `!mise <choix> <montant>` pour miser
• Phase 3: Résultat et gains automatiques

**Types de mises:**
• Numéro exact (0-36): x36
• Couleur (rouge/noir): x2
• Parité (pair/impair): x2
• Moitié (1-18 ou 19-36): x2

💼 **INTÉRIM (Gagner de l'argent):**

**Comment jouer:**
1. Tape `!interim` pour recevoir une commande
2. Clique sur les réactions **dans l'ordre** indiqué
3. Finis avant la fin du temps pour gagner !

**Récompenses:**
• 🥗 Salade: 35€ (12s)
• 🌮 Tacos: 45€ (15s)
• 🍔 Burger: 50€ (20s)
• 🍕 Pizza: 60€ (15s)
• 🍣 Sushi: 70€ (12s)

⚡ **Commandes:**
`!roulette` - Lancer la roulette
`!join` - Rejoindre la partie
`!mise <choix> <montant>` - Miser
`!interim` - Faire un job
`!balance` - Voir son solde
`!leaderboard` - Classement

💵 Solde de départ: **500€**
    """
    
    await ctx.send(text)

@bot.command(name='stop')
async def stop(ctx):
    """Arrête la partie en cours (admin seulement)"""
    global active_roulette
    
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ Seuls les administrateurs peuvent arrêter une partie !")
        return
    
    if active_roulette is None:
        await ctx.send("❌ Aucune partie en cours !")
        return
    
    # Rembourse tous les joueurs qui ont misé
    for user_id, data in active_roulette.players.items():
        if data['bet'] is not None:
            db.add_balance(user_id, data['bet'])
    
    active_roulette = None
    await ctx.send("✅ Partie arrêtée et mises remboursées !")

# Gestion des erreurs
@mise.error
async def mise_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Usage: `!mise <choix> <montant>` - Exemple: `!mise rouge 50`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Le montant doit être un nombre !")

bot.run(os.getenv("DISCORD_TOKEN"))