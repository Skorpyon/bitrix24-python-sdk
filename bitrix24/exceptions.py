"""
Author: Anton Trishenkov anton.trishenkov@gmail.com
Created: 25.01.18
"""

__all__ = ('Bitrix24Error', 'AuthenticationFailed', 'TokenRenewFailed')


class Bitrix24Error(BaseException):
    pass


class AuthenticationFailed(Bitrix24Error):
    def __init__(self, *args, result=None, status_code=None):
        if result is None:
            self.result = {}
        else:
            self.result = result
        self.status_code = status_code
        super().__init__(args)


class TokenRenewFailed(AuthenticationFailed):
    pass
