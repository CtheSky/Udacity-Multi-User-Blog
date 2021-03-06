import os

import webapp2
import jinja2
from google.appengine.ext import db

from validate import valid_username
from validate import valid_password
from model import User
from model import Post
from model import Comment
from model import Like
from hash import make_secure_val
from hash import check_secure_val

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinjia_env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir),
                                autoescape=True)


class Handler(webapp2.RequestHandler):
    """Basic Handler with user authentication helper functions"""
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        params["user"] = self.user
        t = jinjia_env.get_template(template)
        return t.render(params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))

    def set_secure_cookie(self, name, val):
        cookie_val = make_secure_val(val)
        self.response.headers.add_header(
            "Set-Cookie",
            "%s=%s; Path=/" % (name, cookie_val))

    def read_secure_cookie(self, name):
        cookie_val = self.request.cookies.get(name)
        return cookie_val and check_secure_val(cookie_val)

    def login(self, user):
        self.set_secure_cookie("user_id", str(user.key().id()))

    def logout(self):
        self.response.headers.add_header("Set-Cookie", "user_id=; Path=/")

    def initialize(self, *a, **kw):
        webapp2.RequestHandler.initialize(self, *a, **kw)
        uid = self.read_secure_cookie("user_id")
        self.user = uid and User.by_id(int(uid))

    def with_no_user(self):
        self.initialize(self.request, self.response)
        return not self.user

    def user_match_post_author(self, pid):
        self.initialize(self.request, self.response)
        user = self.user
        post = Post.by_id(long(pid))
        return user and user.key().id() == post.uid

    def user_match_comment_author(self, cid):
        self.initialize(self.request, self.response)
        user = self.user
        comment = Comment.by_id(long(cid))
        return user and user.key().id() == comment.uid


class MainPage(Handler):
    """url:/"""
    def get(self):
        """render home page displaying a public post list"""
        self.initialize(self.request, self.response)
        posts = db.GqlQuery("SELECT * FROM Post ORDER BY created DESC")
        self.render("post_main.html", posts=posts)


class NewPost(Handler):
    """url:/new_post"""
    def get(self):
        """render new post page with editor and a form"""
        self.initialize(self.request, self.response)
        if not self.user:
            signin_error = "You have to sign in first."
            self.render("post_main.html", signin_error=signin_error)
        else:
            self.render("new_post.html")

    def post(self):
        """create a post and redirect to MyPost handler"""
        if self.with_no_user():
            self.redirect("/")
            return

        uid = self.user.key().id()
        uname = self.user.name
        title = self.request.get("title")
        subtitle = self.request.get("subtitle", "")
        content = self.request.get("content")

        if title and content:
            content = content.replace('\n', '<br>')
            post = Post(uid=uid,
                        uname=uname,
                        title=title,
                        subtitle=subtitle,
                        content=content)
            post.put()
            self.redirect("/post/" + str(post.key().id()))
        else:
            error = "Both title, subtitle and content are needed!"
            self.render("new_post.html",
                        title=title,
                        content=content,
                        error=error)


class EditPost(Handler):
    """url:/edit_post/pid"""
    def get(self, pid):
        """render edit post page with editor
        including original content and a form"""
        if not self.user_match_post_author(pid):
            self.redirect("/")
            return

        post = Post.by_id(long(pid))
        title = post.title
        subtitle = post.subtitle
        content = post.content

        self.render("edit_post.html",
                    title=title,
                    subtitle=subtitle,
                    content=content)

    def post(self, pid):
        """update the post content"""
        if not self.user_match_post_author(pid):
            self.redirect("/")
            return

        post = Post.get_by_id(long(pid))
        post.subtitle = self.request.get("subtitle", "")
        post.content = self.request.get("content")
        post.put()
        self.redirect("/post/" + str(post.key().id()))


class DeletePost(Handler):
    """url:/delete_post/pid"""
    def post(self, pid):
        """delete post by given id in url"""
        if not self.user_match_post_author(pid):
            self.redirect("/")
            return

        post = Post.by_id(long(pid))
        post.delete()

        self.redirect("/my_post")


class ViewPost(Handler):
    """url:/post/pid"""
    def get(self, pid):
        """render post page including post content
        comments and liked number"""
        pid = long(pid)
        post = Post.by_id(pid)
        if post:
            author = User.by_id(post.uid)
            comments = Comment.by_pid(pid)

            like = None
            if not self.with_no_user():
                like = Like.by_uid_and_pid(self.user.key().id(), pid)
            self.render("post.html",
                        post=post,
                        author=author,
                        comments=comments,
                        like=like)
        else:
            self.render("404.html")


class MyPost(Handler):
    """url:/my_post"""
    def get(self):
        """display a list of posts of user"""
        if self.with_no_user():
            self.redirect("/")
            return

        uid = self.user.key().id()
        posts = Post.by_uid(uid)
        self.render("my_post.html", posts=posts)


class LikePost(Handler):
    """url:/like_post"""
    def post(self):
        """increment post liked number by one"""
        pid = self.request.get("pid")
        if self.with_no_user() or self.user_match_post_author(pid):
            self.redirect("/")
            return

        pid = long(pid)
        post = Post.by_id(pid)
        post.liked += 1
        post.put()

        pid = long(pid)
        like = Like(uid=self.user.key().id(), pid=pid)
        like.put()

        self.redirect("/post/%s" % pid)


class NewComment(Handler):
    """url:/new_comment"""
    def post(self):
        """create a comment to related post"""
        if self.with_no_user():
            self.redirect("/")
            return

        uid = self.user.key().id()
        uname = self.user.name
        pid = long(self.request.get("pid"))
        content = self.request.get("content")

        if content:
            comment = Comment(uid=uid, uname=uname, pid=pid, content=content)
            comment.put()

        self.redirect("/post/%s" % pid)


class DeleteComment(Handler):
    """url:/delete_comment"""
    def post(self):
        """delete comment and redirect to related post page"""
        cid = self.request.get("cid")
        if not self.user_match_comment_author(cid):
            self.redirect("/")
            return

        cid = long(cid)
        pid = long(self.request.get("pid"))
        comment = Comment.by_id(cid)
        comment.delete()

        self.redirect("/post/%s" % pid)


class EditComment(Handler):
    """url:/edit_comment"""
    def post(self):
        """update comment content"""
        cid = self.request.get("cid")
        if not self.user_match_comment_author(cid):
            self.redirect("/")
            return

        cid = long(cid)
        pid = long(self.request.get("pid"))
        content = self.request.get("content")
        comment = Comment.by_id(cid)
        comment.content = content
        comment.put()

        self.redirect("/post/%s" % pid)


class SignUp(Handler):
    """url:/signup"""
    def post(self):
        """create user or give an error message
        if information is not valid"""
        have_error = False
        signup_error = None
        name = self.request.get('username')
        pw = self.request.get('password')
        verify = self.request.get('verify')

        if not valid_password(pw):
            have_error = True
            signup_error = "That wasn't a valid password."
        elif pw != verify:
            have_error = True
            signup_error = "Your passwords didn't match."

        # check duplicate username
        previous_user = User.by_name(name)
        if previous_user:
            have_error = True
            signup_error = "This name has been used, try another one."

        if not valid_username(name):
            have_error = True
            signup_error = "That's not a valid username."

        if have_error:
            self.render("post_main.html",
                        username=name,
                        signup_error=signup_error)
        else:
            user = User.register(name, pw)
            user.put()
            self.login(user)
            self.redirect("/")


class SignIn(Handler):
    """url:/signin"""
    def post(self):
        """make user log in by adding cookie"""
        name = self.request.get('username_si')
        pw = self.request.get('password_si')

        u = User.login(name, pw)
        if u:
            self.login(u)
            self.redirect("/")
        else:
            signin_error = "Invalid username or password."
            self.render("post_main.html",
                        username_si=name,
                        signin_error=signin_error)


class LogOut(Handler):
    """url:/logout"""
    def get(self):
        """make user log out by resetting cookie value"""
        self.logout()
        self.redirect('/')

app = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/new_post', NewPost),
    ('/my_post', MyPost),
    ('/post/(\d+)', ViewPost),
    ('/like_post', LikePost),
    ('/edit_post/(\d+)', EditPost),
    ('/delete_post/(\d+)', DeletePost),
    ('/new_comment', NewComment),
    ('/edit_comment', EditComment),
    ('/delete_comment', DeleteComment),
    ('/signup', SignUp),
    ('/signin', SignIn),
    ('/logout', LogOut)
], debug=True)
