"""Allow ``python -m pokenux`` to use the same CLI as the installed command."""

from pokenux.main import main


raise SystemExit(main())
