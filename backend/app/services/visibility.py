"""Whether a piece of activity is shared with the community or kept private.

The constant lives here and not next to one class of activity because several
share it: reviews and photographs from this issue on, and visits, photo
publications and evaluations as their épicas arrive. A copy per service is a
copy that can drift from the value already written in the database.
"""

PUBLIC = "public"
PRIVATE = "private"
VISIBILITIES = (PUBLIC, PRIVATE)
