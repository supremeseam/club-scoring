# Crew board

Skippers post openings for their boat; sailors offer to crew. Nothing here can change results, ratings, fees or
payments.

## Who can do what

| Login | Created by | Can do |
|---|---|---|
| **Nobody (no login)** | n/a | See the public board (`/crew`); sign up to crew; check or withdraw their own request with the private code shown after signing up (kept in their browser). |
| **Crew account** (optional) | The sailor, at `/crew/join` | Everything above, plus see and withdraw their own sign-ups from any device. |
| **Skipper** | The race committee | For their linked boat(s) only: post/close openings (for any race or one specific race), edit crew notes and contact details, accept or decline requests. |
| **Race committee** | A site administrator | Everything as before, plus *Crew board* in the menu: approve skipper requests, create/link skipper logins, delete spam. A committee member who also sails can be linked to their own boat(s) and then manages that boat's crew exactly like a skipper (see below). |

Each login has a role (`rc`, `skipper`, `crew`) and, separately, a list of linked boats. Only `rc` reaches
`/api/manage/*`; skipper and crew accounts are refused there with 403. A `skipper` or `rc` account can read or change
crew rows only for the boats linked to it; a `crew` account can never be linked to a boat.
Accounts made in the Django admin are `rc`; accounts made through the site are never `rc`.

## Setting up a skipper

1. The skipper opens **Sign in, then "Request a login"** (`/crew/join`) and picks their boat.
2. In **Crew board, Login requests** the committee clicks *Approve*, chooses a username and a temporary password
   (15+ characters) and confirms the boat(s). Or create a login directly under *Skipper logins*.
3. Give the skipper the temporary password. At first sign-in they must choose their own.
4. To reset a skipper's password or disable the login, use the site admin like any other account. Linking a
   second boat, or unlinking one, is under *Skipper logins*.

## Race committee who sail
Under *Crew board, Skipper logins* the committee lists skipper accounts and committee accounts together. Link a boat
to a committee account and that person gets **My boat's crew** in the menu (and the red request count), limited to
their own boats. Their committee access is unchanged, and they can still see every sign-up under *Sign-ups* as before.

## Privacy

A sailor's name, email, phone and message are visible to **the skipper of the boat they asked about and the race
committee only**. The public board shows counts ("2 interested") and the skipper's own posting text. A sailor who
offers to crew on *any boat* for a race is visible to skippers who have an open posting for that race. After a
skipper accepts, the sailor sees the skipper's contact details, but only the route the skipper chose (through the
site, email or phone).

## Notifications

In the app only: a skipper sees a red count in the header and on the *Requests* tab until they respond or press
*Mark all as seen*. No email is sent. (Adding email later means choosing a sender service; nothing in the data
model prevents it.)

## Abuse protection

- Every anonymous write (sign-up, skipper request, crew registration) needs the site's CSRF token, includes a
  hidden "honeypot" field that real people never fill, and is limited per address per hour (sign-ups 6, skipper
  requests 3, registrations 3). Only a salted hash of the address is stored, and it is deleted after two days.
- One sailor can't sign up for the same target twice, and a boat holds at most 40 waiting requests.
- Field lengths are capped, emails validated, and passwords follow the same policy as every other account.
- Spam that gets through: delete it under *Crew board, Sign-ups*.
- Not covered: a determined person using many addresses. If the board is attacked, put a CAPTCHA or CDN rate limit
  in front, or set the sign-ups to require an account.
