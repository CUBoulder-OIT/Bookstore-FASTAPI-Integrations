"""" defines fastapi bookstore endpoints """

import datetime
import logging
import random
import secrets
import string
import time
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.params import Query
from fastapi.security import HTTPBasic, HTTPBasicCredentials

# app-specific modules and packages
import app.graphql.graphql as gql
from app.utility.utility import create_books

from . import config

logging.config.fileConfig("app/logging.conf", disable_existing_loggers=False)

logger = logging.getLogger(__name__)

app = FastAPI()
security = HTTPBasic()


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Tidy bit of logging assist to show how long each call takes.
    Found here: https://philstories.medium.com/fastapi-logging-f6237b84ea64
    """
    idem = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    logger.info("rid=%s start request path=%s", idem, request.url.path)
    start_time = time.time()

    response = await call_next(request)

    process_time = (time.time() - start_time) * 1000
    formatted_process_time = "{0:.2f}".format(process_time)
    logger.info(
        "rid=%s completed_in=%sms status_code=%s",
        idem,
        formatted_process_time,
        response.status_code,
    )

    return response


@app.get("/ready")
def read_root():
    """ ready status by way of returned datetime """
    return {
        "Hello": datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()
    }


# pylint: disable=too-many-arguments,unused-argument
@app.get("/SBookInfo")
def read_item(
    response: Response,
    credentials: HTTPBasicCredentials = Depends(security),
    course1: Optional[List[str]] = Query(None),
    session1: Optional[List[str]] = Query(None),
    section1: Optional[List[str]] = Query(None),
    term1: Optional[List[str]] = Query(None),
    dept1: Optional[List[str]] = Query(None),
    is_json: bool = False,
):
    """
    Rebuilding under an existing service.

    Basic user/password auth.

    Note the duplicate session1 queries args, for ex:
    https://ws.colorado.edu/BookStore/SBookInfo?course1=ACCT3230&session1=001&session1=B&term1=2217
    """

    correct_username = secrets.compare_digest(
        credentials.username, config.settings.basic_username
    )
    correct_password = secrets.compare_digest(
        credentials.password, config.settings.basic_password
    )
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Basic"},
        )

    # Call the GraphQL service to fetch data
    gql_status, results = gql.make_request(
        url=config.settings.graphql_url,
        api_key=config.settings.graphql_key,
        courses=course1,
        sections=section1,
        terms=term1,
        sessions=session1,
    )

    # return or replace the status_code with what's received from the make_request()
    response.status_code = gql_status

    # pylint: disable=no-else-return
    if gql_status == 200:
        if len(results) > 0:
            if is_json:
                return results
            else:
                # convert to XML and return it.
                books_xml = create_books(results)
                return Response(content=books_xml, media_type="application/xml")
        else:
            return {"No data returned."}
    elif gql_status == 424:
        logger.error("gql_status: %s, %s", gql_status, results)
        return {"An error with the backend service has occurred."}
    else:
        logger.error("gql_status: %s, %s", gql_status, results)
        return {"An internal error has occurred."}
