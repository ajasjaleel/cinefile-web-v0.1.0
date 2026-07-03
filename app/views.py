from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator  # Required for pages (48 movies per page)
from .models import Franchise, Movie, WatchedMovie, Watchlist
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Max, Count, Q
from django.contrib.auth import login
from django.core.cache import cache
from django.utils import timezone
from collections import Counter
import datetime
import math


# 1. The Home Page
def franchise_list(request):
    franchises = Franchise.objects.all().order_by('name')
    return render(request, 'franchise_list.html', {'franchises': franchises})


# 2. The Franchise Detail Page
def franchise_detail(request, franchise_id):
    franchise = get_object_or_404(Franchise, id=franchise_id)
    movies = franchise.movies.all().order_by('chronological_order')

    if request.user.is_authenticated:
        watched_movie_ids = WatchedMovie.objects.filter(
            user=request.user,
            movie__in=movies
        ).values_list('movie_id', flat=True)
    else:
        watched_movie_ids = []

    return render(request, 'franchise_detail.html', {
        'franchise': franchise,
        'movies': movies,
        'watched_movie_ids': set(watched_movie_ids)
    })


# 3. The Checkbox Toggle logic
@login_required(login_url='/login/')
def toggle_watched(request, movie_id):
    if request.method == "POST":
        movie = get_object_or_404(Movie, id=movie_id)

        # FIX #4: get_or_create() is atomic at the DB level, so two near-simultaneous
        # POSTs can't both "see" no record and both insert one.
        # This still requires unique_together = ('user', 'movie') on the WatchedMovie
        # model (+ a migration) so the DB itself rejects a duplicate row if the race
        # is somehow still hit (e.g. on a backend without SELECT ... FOR UPDATE support).
        watched_record, created = WatchedMovie.objects.get_or_create(
            user=request.user,
            movie=movie
        )

        if not created:
            # It already existed, so this click means "uncheck it"
            watched_record.delete()
            cache.delete(f"recommendations:user:{request.user.id}")
            return JsonResponse({'status': 'unchecked'})

        cache.delete(f"recommendations:user:{request.user.id}")
        return JsonResponse({'status': 'checked'})

    return JsonResponse({'error': 'Invalid request'}, status=400)


@login_required(login_url='/login/')
def toggle_watchlist(request, movie_id):
    if request.method == "POST":
        movie = get_object_or_404(Movie, id=movie_id)

        watchlist_record, created = Watchlist.objects.get_or_create(
            user=request.user,
            movie=movie
        )

        if not created:
            watchlist_record.delete()
            return JsonResponse({'status': 'removed'})

        return JsonResponse({'status': 'added'})

    return JsonResponse({'error': 'Invalid request'}, status=400)

# 4. The Individual Movie Detail Page
def movie_detail(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)

    if request.user.is_authenticated:
        is_watched = WatchedMovie.objects.filter(user=request.user, movie=movie).exists()
        is_in_watchlist = Watchlist.objects.filter(user=request.user, movie=movie).exists()
    else:
        is_watched = False
        is_in_watchlist = False

    return render(request, 'movie_detail.html', {
        'movie': movie,
        'is_watched': is_watched,
        'is_in_watchlist': is_in_watchlist,
    })


# 5. The ALL MOVIES Directory 
def all_movies(request):
    movies = Movie.objects.select_related('franchise').all()

    genre_query = request.GET.get('genre')
    if genre_query:
        movies = movies.filter(genres__icontains=genre_query)

    sort_query = request.GET.get('sort', '-release_year')
    if sort_query == 'title':
        movies = movies.order_by('title')
    elif sort_query == '-vote_average':
        movies = movies.order_by('-vote_average', '-release_year')
    else:
        movies = movies.order_by('-release_year', 'title')

    paginator = Paginator(movies, 48)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    if request.user.is_authenticated:
        watched_movie_ids = WatchedMovie.objects.filter(
            user=request.user,
            movie__in=page_obj.object_list
        ).values_list('movie_id', flat=True)
    else:
        watched_movie_ids = []

    popular_genres = [
        'Action', 'Adventure', 'Animation', 'Comedy', 'Crime',
        'Documentary', 'Drama', 'Family', 'Fantasy', 'Horror',
        'Mystery', 'Romance', 'Science Fiction', 'Thriller'
    ]

    querystring = request.GET.copy()
    querystring.pop('page', None)

    return render(request, 'all_movies.html', {
        'page_obj': page_obj,
        'watched_movie_ids': set(watched_movie_ids),
        'current_genre': genre_query,
        'current_sort': sort_query,
        'genres': popular_genres,
        'querystring': querystring.urlencode(),
    })


# 6. Create Account / Signup
def signup(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            email = request.POST.get('email', '').strip()
            if email:
                user.email = email
                user.save()
            login(request, user)
            return redirect('franchise_list')
    else:
        form = UserCreationForm()

    return render(request, 'account/signup.html', {'form': form})



@login_required(login_url='/login/')
def watched_status(request):
    """Return which movies the user has watched (for bfcache sync)"""
    ids_param = request.GET.get('ids', '')
    movie_ids = [int(i) for i in ids_param.split(',') if i.isdigit()]
    
    watched = set(
        WatchedMovie.objects.filter(
            user=request.user, movie_id__in=movie_ids
        ).values_list('movie_id', flat=True)
    )
    
    return JsonResponse({'watched': list(watched)})

@login_required(login_url='/login/')
def watchlist_status(request):
    """Return the user's current watchlist movie ids (for bfcache sync on profile page)"""
    watchlist_ids = list(
        Watchlist.objects.filter(user=request.user).values_list('movie_id', flat=True)
    )
    return JsonResponse({'watchlist': watchlist_ids})

def search(request):
    query = request.GET.get("q", "").strip()
    movies = Movie.objects.none()
    franchises = Franchise.objects.none()
 
    if query:
        movies = Movie.objects.filter(
            Q(title__icontains=query) |
            Q(overview__icontains=query) |
            Q(tagline__icontains=query) |
            Q(distributor__icontains=query)
        )
        franchises = Franchise.objects.filter(name__icontains=query)
 
    return render(request, "profile-search/search.html", {
        "query": query,
        "movies": movies,
        "franchises": franchises,
    })
 

def _compute_recommendations(user, limit=20):
    watched = WatchedMovie.objects.filter(user=user).select_related('movie', 'movie__franchise')
    watched_list = list(watched)
    watched_movie_ids = {w.movie_id for w in watched_list}

    watchlist_ids = set(
        Watchlist.objects.filter(user=user).values_list('movie_id', flat=True)
    )
    excluded_ids = watched_movie_ids | watchlist_ids

    # ---- Cold start: no watch history yet ----
    if not watched_list:
        return list(
            Movie.objects.exclude(id__in=excluded_ids)
            .order_by('-release_year')[:limit]
        )

    # ---- 1. Genre rarity weights (like IDF) ----
    # Rare genres in the catalog are more "distinctive" — matching one means more.
    total_movie_count = Movie.objects.count() or 1
    genre_doc_count = Counter()
    for genres_str in Movie.objects.values_list('genres', flat=True):
        if not genres_str:
            continue
        for g in {g.strip() for g in genres_str.split(',') if g.strip()}:
            genre_doc_count[g] += 1

    genre_rarity = {
        g: math.log(total_movie_count / (count + 1)) + 1
        for g, count in genre_doc_count.items()
    }

    # ---- 2. User's genre taste, weighted by recency ----
    now = timezone.now()
    genre_taste = Counter()
    franchise_watch_counts = Counter()

    for w in watched_list:
        movie = w.movie

        # Recency decay: watched_at within last 30 days = full weight,
        # decaying down to a floor of 0.3 for very old watches.
        watched_at = getattr(w, 'watched_at', None)
        if watched_at:
            days_ago = max((now - watched_at).days, 0)
            recency_weight = max(0.3, math.exp(-days_ago / 90))
        else:
            recency_weight = 0.6  # unknown timestamp, assume moderate

        if movie.genres:
            for g in {g.strip() for g in movie.genres.split(',') if g.strip()}:
                genre_taste[g] += recency_weight * genre_rarity.get(g, 1)

        if movie.franchise_id:
            franchise_watch_counts[movie.franchise_id] += 1

    if not genre_taste:
        return list(
            Movie.objects.exclude(id__in=excluded_ids)
            .order_by('-release_year')[:limit]
        )

    # Normalize taste weights to 0–1 so scores are comparable across users
    max_taste = max(genre_taste.values())
    genre_taste = {g: v / max_taste for g, v in genre_taste.items()}

    # ---- 3. Score every unwatched candidate ----
    candidates = Movie.objects.exclude(id__in=excluded_ids).select_related('franchise')

    scored = []
    for movie in candidates:
        if not movie.genres:
            continue

        movie_genres = {g.strip() for g in movie.genres.split(',') if g.strip()}
        if not movie_genres:
            continue

        genre_score = sum(genre_taste.get(g, 0) for g in movie_genres) / len(movie_genres)

        # Franchise bonus: user has already started this franchise
        franchise_bonus = 0
        if movie.franchise_id and franchise_watch_counts.get(movie.franchise_id):
            franchise_bonus = 0.5  # flat, meaningful boost — "you're already invested"

        # Mild recency-of-release nudge as a tiebreaker, not a driver
        release_nudge = (movie.release_year or 0) / 10000

        total_score = genre_score + franchise_bonus + release_nudge
        scored.append((total_score, movie))

    scored.sort(key=lambda pair: pair[0], reverse=True)

    # ---- 4. Diversity cap: max 3 picks per franchise, so one franchise
    # doesn't fill the entire rail ----
    final = []
    franchise_count_in_results = Counter()
    for score, movie in scored:
        fid = movie.franchise_id
        if fid and franchise_count_in_results[fid] >= 3:
            continue
        final.append(movie)
        if fid:
            franchise_count_in_results[fid] += 1
        if len(final) >= limit:
            break

    return final


@login_required
def profile(request):
    watchlist_qs = Watchlist.objects.filter(
        user=request.user
    ).select_related('movie', 'movie__franchise').order_by('-added_at')

    watchlist_movies = [w.movie for w in watchlist_qs]

    # Cache per-user for 30 minutes — this loop touches the full movie
    # catalog, so we don't want it recomputed on every profile page load.
    cache_key = f"recommendations:user:{request.user.id}"
    recommended_movies = cache.get(cache_key)
    if recommended_movies is None:
        recommended_movies = _compute_recommendations(request.user, limit=20)
        cache.set(cache_key, recommended_movies, timeout=60 * 30)

    return render(request, "profile-search/profile.html", {
        "user": request.user,
        "watchlist_movies": watchlist_movies,
        "recommended_movies": recommended_movies,
    })


def _build_franchise_data(franchises_qs, user, last_watched_map=None):
    """
    Same .filter(movie__in=...) pattern as franchise_detail() — avoids the
    guessed related_name issue from before entirely.
    """
    last_watched_map = last_watched_map or {}
    data = []
    for franchise in franchises_qs:
        movies = franchise.movies.all().order_by('chronological_order')
        f_watched_ids = set(
            WatchedMovie.objects.filter(
                user=user, movie__in=movies
            ).values_list('movie_id', flat=True)
        )
        total_count = movies.count()
        watched_count = len(f_watched_ids)
        percent = int((watched_count / total_count) * 100) if total_count else 0
        data.append({
            'franchise': franchise,
            'movies': movies,
            'watched_ids': f_watched_ids,
            'watched_count': watched_count,
            'total_count': total_count,
            'percent': percent,
            'last_watched': last_watched_map.get(franchise.id),
        })
    return data


def _franchise_ids_and_last_watched(user):
    all_watched = WatchedMovie.objects.filter(
        user=user
    ).select_related('movie', 'movie__franchise')

    franchise_ids = set()
    last_watched_per_franchise = {}

    for w in all_watched:
        franchise = w.movie.franchise
        if franchise is None:
            continue
        franchise_ids.add(franchise.id)

        ts = getattr(w, 'watched_at', None)
        if ts and (
            franchise.id not in last_watched_per_franchise
            or ts > last_watched_per_franchise[franchise.id]
        ):
            last_watched_per_franchise[franchise.id] = ts

    return franchise_ids, last_watched_per_franchise


@login_required(login_url='/login/')
def watched_list(request):
    """Home watched page — two horizontal preview rails."""

    watched_qs = WatchedMovie.objects.filter(
        user=request.user
    ).select_related('movie', 'movie__franchise').order_by('-watched_at')

    total_movies_watched = watched_qs.count()
    watched_movies = [w.movie for w in watched_qs[:30]]  # capped for the rail

    franchise_ids, last_watched_per_franchise = _franchise_ids_and_last_watched(request.user)
    franchises_watched = Franchise.objects.filter(id__in=franchise_ids)

    franchise_data = _build_franchise_data(
        franchises_watched, request.user, last_watched_per_franchise
    )
    epoch = datetime.datetime.min.replace(tzinfo=timezone.utc)
    franchise_data.sort(key=lambda d: d['last_watched'] or epoch, reverse=True)

    return render(request, 'watched/watched_list.html', {
        'watched_movies': watched_movies,
        'total_movies_watched': total_movies_watched,
        'franchise_data': franchise_data,
        'total_franchises_watched': len(franchise_data),
    })


@login_required(login_url='/login/')
def watched_movies_all(request):
    """Show All → full filterable grid of every watched movie."""
    watched_qs = WatchedMovie.objects.filter(
        user=request.user
    ).select_related('movie', 'movie__franchise')

    genre = request.GET.get('genre')
    if genre:
        watched_qs = watched_qs.filter(movie__genres__icontains=genre)

    sort = request.GET.get('sort', '-watched_at')
    if sort == 'title':
        watched_qs = watched_qs.order_by('movie__title')
    else:
        sort = '-watched_at'
        watched_qs = watched_qs.order_by('-watched_at')

    watched_movies = [w.movie for w in watched_qs]

    popular_genres = [
        'Action', 'Adventure', 'Animation', 'Comedy', 'Crime',
        'Documentary', 'Drama', 'Family', 'Fantasy', 'Horror',
        'Mystery', 'Romance', 'Science Fiction', 'Thriller'
    ]

    return render(request, 'watched/watched_movies_all.html', {
        'watched_movies': watched_movies,
        'current_genre': genre,
        'current_sort': sort,
        'genres': popular_genres,
    })


@login_required(login_url='/login/')
def watched_franchises_all(request):
    """Show All → full sortable list of every franchise started."""
    franchise_ids, last_watched_per_franchise = _franchise_ids_and_last_watched(request.user)
    franchises_watched = Franchise.objects.filter(id__in=franchise_ids)

    sort = request.GET.get('sort', '-last_watched')
    if sort == 'title':
        franchises_watched = franchises_watched.order_by('name')

    franchise_data = _build_franchise_data(
        franchises_watched, request.user, last_watched_per_franchise
    )

    if sort != 'title':
        sort = '-last_watched'
        epoch = datetime.datetime.min.replace(tzinfo=timezone.utc)
        franchise_data.sort(key=lambda d: d['last_watched'] or epoch, reverse=True)

    return render(request, 'watched/watched_franchises_all.html', {
        'franchise_data': franchise_data,
        'current_sort': sort,
    })

from django.http import HttpResponse
from django.core.mail import send_mail

def test_smtp(request):
    send_mail(
        subject="SMTP Test",
        message="If you received this email, Brevo SMTP is working!",
        from_email=None,  # Uses DEFAULT_FROM_EMAIL
        recipient_list=["ajasjaleel529@gmail.com"],
        fail_silently=False,
    )

    return HttpResponse("Test email sent successfully!")
