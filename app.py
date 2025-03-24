from werkzeug.security import check_password_hash
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin
from flask import flash
from flask_wtf.csrf import CSRFProtect
from flask import Flask, render_template, request, redirect, url_for, session
from config import DevelopmentConfig
from flask import g
from forms import PizzaForm, ClienteForm, loginForm, logoutForm
from models import db
from models import Venta, DetallePizza, IngredientePizza, Usuario
import json

app = Flask(__name__)
app.config.from_object(DevelopmentConfig)
csrf = CSRFProtect()
login_manager_app = LoginManager(app)

@login_manager_app.user_loader
def load_user(id):
    return Usuario.query.get(int(id))

@app.route('/')
def index():
    return redirect(url_for('login'))



PRECIOS = {
    'pequena': 40,
    'mediana': 80,
    'grande': 120
}

COSTO_INGREDIENTE = 10


def agregarPizza(tamano, cantidad, ingredientes):
    ingredientes_lista = ",".join(ingredientes)
    with open("pedidos.txt", "a", encoding="utf-8") as archivo:
        archivo.write(f"{tamano}|{cantidad}|{ingredientes_lista}\n")


def cargarCarrito():
    carrito = []
    try:
        with open("pedidos.txt", "r", encoding="utf-8") as archivo:
            for linea in archivo:
                datos = linea.strip().split("|")
                if len(datos) >= 3:
                    carrito.append({
                        "tamano": datos[0],
                        "cantidad": datos[1],
                        "ingredientes": datos[2].split(",") if datos[2] else []
                    })
    except FileNotFoundError:
        with open("pedidos.txt", "w", encoding="utf-8") as archivo:
            pass
    return carrito


def eliminarPizzaEspecifica(indice):
    carrito = cargarCarrito()
    if 0 <= indice < len(carrito):
        carrito.pop(indice)
        with open("pedidos.txt", "w", encoding="utf-8") as archivo:
            for pizza in carrito:
                ingredientes_lista = ",".join(pizza["ingredientes"])
                archivo.write(
                    f"{pizza['tamano']}|{pizza['cantidad']}|{ingredientes_lista}\n")
        return True
    return False


def vaciarCarrito():
    open("pedidos.txt", "w").close()


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.route("/pizza", methods=['GET', 'POST'])
@login_required
def pizza():
    
    pizza_form = PizzaForm()
    cliente_form = ClienteForm()

    if 'cliente_data' in session:
        cliente_form.nombre.data = session['cliente_data'].get('nombre', '')
        cliente_form.direccion.data = session['cliente_data'].get(
            'direccion', '')
        cliente_form.telefono.data = session['cliente_data'].get(
            'telefono', '')

    if request.method == 'POST' and pizza_form.validate_on_submit():
        session['cliente_data'] = {
            'nombre': cliente_form.nombre.data,
            'direccion': cliente_form.direccion.data,
            'telefono': cliente_form.telefono.data
        }

        if not pizza_form.ingredientes.data:
            flash('Debes seleccionar al menos un ingrediente', 'danger')
            return redirect(url_for('index'))

        agregarPizza(pizza_form.tamano.data, pizza_form.numPizzas.data,
                     pizza_form.ingredientes.data)
        flash('Pizza agregada al carrito', 'success')
        return redirect(url_for('index'))

    carrito = cargarCarrito()

    ventas_hoy = []
    ventas_mes = []
    total_ventas_hoy = 0
    total_ventas_mes = 0
    
    try:

        ventas_hoy = Venta.query.filter(db.func.date(
            Venta.fecha) == db.func.current_date()).all()
        total_ventas_hoy = sum(venta.total_venta for venta in ventas_hoy)
        ventas_mes = Venta.query.filter(
        db.func.extract('year', Venta.fecha) == db.func.extract('year', db.func.current_date()),
        db.func.extract('month', Venta.fecha) == db.func.extract('month', db.func.current_date())
        ).all()
        total_ventas_mes = sum(venta.total_venta for venta in ventas_mes)
        
    except:
        ventas_hoy = []
        ventas_mes = []
        

    return render_template('index.html',
                           pizza_form=pizza_form,
                           cliente_form=cliente_form,
                           carrito=carrito,
                           ventas_hoy=ventas_hoy,
                           ventas_mes=ventas_mes,
                           total_ventas_mes=total_ventas_mes,
                           total_ventas_hoy=total_ventas_hoy)


@app.route('/finalizarPedido', methods=['GET', 'POST'])
def finalizarPedido():
    cliente_form = ClienteForm()
    pizzas = cargarCarrito()

    if not pizzas:
        flash("No hay pizzas en el carrito", "danger")
        return redirect(url_for('index'))

    if request.method == 'POST':
        if cliente_form.validate_on_submit():
            nombre = cliente_form.nombre.data
            direccion = cliente_form.direccion.data
            telefono = cliente_form.telefono.data

            session['cliente_data'] = {
                'nombre': nombre,
                'direccion': direccion,
                'telefono': telefono
            }
        elif 'cliente_data' in session:
            nombre = session['cliente_data'].get('nombre')
            direccion = session['cliente_data'].get('direccion')
            telefono = session['cliente_data'].get('telefono')
        else:
            flash("Por favor complete los datos del cliente", "danger")
            return redirect(url_for('index'))

        if not nombre or not direccion or not telefono:
            flash("Por favor complete todos los datos del cliente", "danger")
            return redirect(url_for('index'))

        subtotal_total = 0
        for pizza in pizzas:
            precio_inicial = PRECIOS[pizza["tamano"]]
            precio_ingredientes = len(
                pizza["ingredientes"]) * COSTO_INGREDIENTE
            subtotal_pieza = precio_inicial + precio_ingredientes
            subtotal_total += subtotal_pieza * int(pizza["cantidad"])

        nueva_venta = Venta(
            nombre_cliente=nombre,
            direccion_cliente=direccion,
            telefono_cliente=telefono,
            total_venta=subtotal_total
        )

        db.session.add(nueva_venta)
        db.session.flush()

        for pizza in pizzas:
            precio_inicial = PRECIOS[pizza["tamano"]]
            precio_ingredientes = len(
                pizza["ingredientes"]) * COSTO_INGREDIENTE
            subtotal_pieza = precio_inicial + precio_ingredientes
            subtotal_total_pizza = subtotal_pieza * int(pizza["cantidad"])

            detalle = DetallePizza(
                venta_id=nueva_venta.id,
                tamano=pizza["tamano"],
                cantidad=pizza["cantidad"],
                subtotal=subtotal_total_pizza
            )

            db.session.add(detalle)
            db.session.flush()

            for ingrediente in pizza["ingredientes"]:
                ing = IngredientePizza(
                    detalle_pizza_id=detalle.id,
                    nombre_ingrediente=ingrediente
                )
                db.session.add(ing)

        try:
            db.session.commit()
            vaciarCarrito()
            flash("Pedido finalizado correctamente", "success")
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error al procesar el pedido: {str(e)}", "danger")
            return redirect(url_for('index'))

    return redirect(url_for('index'))


@app.route('/eliminar_pizza/<int:indice>', methods=['POST'])
def eliminar_pizza(indice):
    if eliminarPizzaEspecifica(indice):
        flash("Pizza eliminada del carrito", "success")
    else:
        flash("No se pudo eliminar la pizza", "danger")
    return redirect(url_for('index'))


@app.route('/eliminar_carrito', methods=['POST'])
def eliminar_carrito():
    vaciarCarrito()
    flash("Carrito vaciado correctamente", "info")
    return redirect(url_for('index'))

def status_401(error):
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = loginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data

        user = Usuario.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):  # Comparar contraseñas
            session['id'] = user.id
            session['username'] = user.username
            session["password"] = user.password
            login_user(user)
            flash('Login exitoso', 'success')
            return redirect(url_for('pizza'))  # Redirigir a una página de inicio después del login
        else:
            flash('Usuario o contraseña incorrectos', 'danger')

    return render_template('auth/login.html', form=form)

@app.route('/logout', methods=['POST'])
def logout():
    logout_user()  # Cierra la sesión
    flash("Has cerrado sesión exitosamente", "success")  # Mensaje opcional
    return redirect(url_for('login'))

if __name__ == '__main__':
    csrf.init_app(app)
    db.init_app(app)
    app.register_error_handler(401,status_401)
    with app.app_context():
        db.create_all()
    app.run()
