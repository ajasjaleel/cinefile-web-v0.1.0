from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.franchise_list, name='franchise_list'),
    # --- Authentication URLs ---
    path('login/', auth_views.LoginView.as_view(template_name='account/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    # ADDED: This maps to the custom signup view in views.py
    path('signup/', views.signup, name='signup'), 

    # --- Password reset URLs ---
    path(
    'password-reset/',
        auth_views.PasswordResetView.as_view(
            template_name='password/password_reset.html',

            # Plain-text fallback
            email_template_name='password/password_reset_email.txt',

            # HTML email
            html_email_template_name='password/password_reset_email.html',

            # Subject
            subject_template_name='password/password_reset_subject.txt',
        ),
        name='password_reset'
    ),
    path('password-reset/done/',
        auth_views.PasswordResetDoneView.as_view(template_name='password/password_reset_done.html'),
        name='password_reset_done'),
    path('reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(template_name='password/password_reset_confirm.html'),
        name='password_reset_confirm'),
    path('reset/done/',
        auth_views.PasswordResetCompleteView.as_view(template_name='password/password_reset_complete.html'),
        name='password_reset_complete'),


    # --- Movie & Franchise URLs ---
    path('franchise/<int:franchise_id>/', views.franchise_detail, name='franchise_detail'),
    path('toggle/<int:movie_id>/', views.toggle_watched, name='toggle_watched'),
    path('movie/<int:movie_id>/', views.movie_detail, name='movie_detail'),
    path('movies/', views.all_movies, name='all_movies'),
    path('watched-status/', views.watched_status, name='watched_status'),
    path('watchlist-status/', views.watchlist_status, name='watchlist_status'),
    
    path('watched/', views.watched_list, name='watched_list'),
    path('watched/movies/', views.watched_movies_all, name='watched_movies_all'),
    path('watched/franchises/', views.watched_franchises_all, name='watched_franchises_all'),
    path("search/", views.search, name="search"),
    path("profile/", views.profile, name="profile"),
    path('toggle-watchlist/<int:movie_id>/', views.toggle_watchlist, name='toggle_watchlist'),
]