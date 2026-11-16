import datetime

from java.util import Date, Set  # type: ignore[import-not-found]
import jep  # type: ignore[import-not-found]

jep.setJavaToPythonConverter(Date, lambda jdate: datetime.datetime.fromtimestamp(jdate.getTime() / 1000, datetime.UTC))
jep.setJavaToPythonConverter(Set, set)  # java.lang.Iterable → __iter__ provided by JEP
